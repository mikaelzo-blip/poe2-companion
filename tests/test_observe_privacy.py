"""Tests for fail-closed privacy filter and log anomaly grouper."""

import pytest

from companion.observe.privacy import PrivacyFilter, PrivacyResult
from companion.observe.anomalies import LogAnomalyGrouper


def test_privacy_filter_chat_rejection():
    pf = PrivacyFilter()
    chat_lines = [
        "2026/09/23 14:00:00 123456 [INFO] @From CoolGamer: hey want to trade?",
        "2026/09/23 14:00:01 123456 [INFO] @To BestFriend: be right there",
        "2026/09/23 14:00:02 123456 [INFO] #global Hello global chat!",
        "2026/09/23 14:00:03 123456 [INFO] $trade WTS Mirror of Kalandra 500ex",
        "2026/09/23 14:00:04 123456 [INFO] %party Let's clear the boss",
        "2026/09/23 14:00:05 123456 [INFO] &guild Anyone for maps?",
        "2026/09/23 14:00:06 123456 [INFO] !local Watch out for ground degen!",
    ]
    for line in chat_lines:
        res = pf.evaluate_line(line)
        assert not res.is_safe, f"Expected unsafe for: {line}"
        assert res.is_chat, f"Expected is_chat=True for: {line}"
        assert res.sanitized_text is None


def test_privacy_filter_credential_rejection():
    pf = PrivacyFilter()
    cred_lines = [
        "2026/09/23 14:00:00 [DEBUG] Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token",
        "2026/09/23 14:00:00 [DEBUG] oauth_token=secret_oauth_token_12345",
        "2026/09/23 14:00:00 [DEBUG] password='mySuperSecretPassword!'",
        "2026/09/23 14:00:00 [DEBUG] Authorization: Bearer abcdef1234567890",
    ]
    for line in cred_lines:
        res = pf.evaluate_line(line)
        assert not res.is_safe
        assert res.has_credentials
        assert res.sanitized_text is None


def test_privacy_filter_approved_debug_envelope_sanitization():
    pf = PrivacyFilter()
    line = "2026/09/23 14:00:00 12345678 abc [ENGINE] Resource loaded at 0x7fff89ab with id 12345"
    res = pf.evaluate_line(line)
    assert res.is_safe
    assert not res.is_chat
    assert not res.has_credentials
    assert res.is_approved_envelope
    assert not res.uncertain
    assert res.sanitized_text is not None
    assert "0x7fff89ab" not in res.sanitized_text
    assert "<HEX>" in res.sanitized_text


def test_privacy_filter_ambiguous_line_uncertain():
    pf = PrivacyFilter()
    line = "Mysterious unstructured line with arbitrary player note or unknown text"
    res = pf.evaluate_line(line)
    # Not chat, not credentials, but not approved envelope -> uncertain
    assert res.uncertain
    assert not res.is_approved_envelope


def test_anomaly_grouper_discards_chat_and_credentials():
    grouper = LogAnomalyGrouper()
    grouper.record_line("@From Player: buying your divine orb")
    grouper.record_line("Authorization: Bearer secret_token")
    assert len(grouper.get_signatures()) == 0


def test_anomaly_grouper_withholds_uncertain_representative_text():
    grouper = LogAnomalyGrouper()
    line = "2026/09/23 14:00:00 Something arbitrary without known engine envelope"
    record = grouper.record_line(line)
    assert record is not None
    assert record.privacy_sample_withheld is True
    assert len(record.sanitized_samples) == 0
    assert record.occurrence_count == 1
    assert record.pattern_hash is not None


def test_anomaly_grouper_samples_approved_envelope_up_to_cap():
    grouper = LogAnomalyGrouper()
    for i in range(5):
        line = f"2026/09/23 14:0{i}:00 123456 [ENGINE] Texture allocation failed code {i} at 0x{i}abc"
        grouper.record_line(line)

    signatures = grouper.get_signatures()
    assert len(signatures) == 1
    sig = signatures[0]
    assert sig.occurrence_count == 5
    assert sig.privacy_sample_withheld is False
    assert sig.sanitized_samples == ["[ENGINE] Texture allocation failed code <CODE> at <HEX>"]
    assert len(sig.sanitized_samples) <= grouper.MAX_SAMPLES_PER_SIGNATURE


@pytest.mark.parametrize("line,private", [
    ('2026/09/23 14:00:00 [DEBUG] note="my arbitrary private diary"', "my arbitrary private diary"),
    ("2026/09/23 14:00:00 [SYSTEM] contact user@example.test", "user@example.test"),
    ("2026/09/23 14:00:00 [ENGINE] path C:/Users/PrivatePerson/save.txt", "PrivatePerson"),
    ("2026/09/23 14:00:00 [ENGINE] fetch https://example.test/?q=privateword", "privateword"),
    ("2026/09/23 14:00:00 [DEBUG] raw opaqueTokenXYZ123456789", "opaqueTokenXYZ"),
    ("2026/09/23 14:00:00 [INFO] user said Connecting to [ENGINE] something", "user said"),
    ("2026/09/23 14:00:00 [ENGINE] Resource loaded at 0xabc with id 12345 extra privateword", "privateword"),
])
def test_unstructured_debug_samples_are_withheld(line, private):
    result = PrivacyFilter().evaluate_line(line)
    assert result.uncertain or not result.is_safe
    rec = LogAnomalyGrouper().record_line(line)
    if rec is not None:
        assert rec.privacy_sample_withheld is True
        assert rec.sanitized_samples == []
        assert private not in str(rec.model_dump())


def test_anomaly_grouper_signature_cap_at_100():
    grouper = LogAnomalyGrouper()
    for i in range(150):
        # Different patterns
        line = f"2026/09/23 14:00:00 123456 [SYSTEM] Unknown event variant_{i}"
        grouper.record_line(line)

    signatures = grouper.get_signatures()
    assert len(signatures) <= 100
