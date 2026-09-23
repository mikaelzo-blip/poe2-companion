"""Privacy-safe log anomaly aggregation and signature grouping."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Sequence

from companion.observe.models import AnomalySignatureRecord
from companion.observe.privacy import PrivacyFilter


class LogAnomalyGrouper:
    """Groups unrecognized log lines into privacy-bounded anomaly signatures."""

    MAX_SIGNATURES = 100
    MAX_SAMPLES_PER_SIGNATURE = 3

    def __init__(self, privacy_filter: PrivacyFilter | None = None) -> None:
        self.privacy_filter = privacy_filter or PrivacyFilter()
        self._signatures: dict[str, AnomalySignatureRecord] = {}

    _NUM_NORM_RE = re.compile(r"\b\d+\b")

    def _hash_pattern(self, sanitized: str) -> str:
        """Derive a stable 16-character SHA-256 pattern signature by normalizing digits."""
        template = self._NUM_NORM_RE.sub("<NUM>", sanitized)
        return hashlib.sha256(template.encode("utf-8")).hexdigest()[:16]

    def record_line(self, line: str) -> AnomalySignatureRecord | None:
        """Inspect and record an unparsed log line under strict privacy bounds."""
        eval_result = self.privacy_filter.evaluate_line(line)
        if not eval_result.is_safe:
            # Completely discard whispers, chat, and credentials
            return None

        sanitized = eval_result.sanitized_text or "UNKNOWN"
        pattern_hash = self._hash_pattern(sanitized)
        now_iso = datetime.now(timezone.utc).isoformat()

        if pattern_hash in self._signatures:
            existing = self._signatures[pattern_hash]
            samples = list(existing.sanitized_samples)
            if (
                not eval_result.uncertain
                and len(samples) < self.MAX_SAMPLES_PER_SIGNATURE
                and eval_result.sanitized_text
                and eval_result.sanitized_text not in samples
            ):
                samples.append(eval_result.sanitized_text)

            updated = AnomalySignatureRecord(
                pattern_hash=existing.pattern_hash,
                classification=existing.classification,
                occurrence_count=existing.occurrence_count + 1,
                first_seen_at=existing.first_seen_at,
                last_seen_at=now_iso,
                privacy_sample_withheld=existing.privacy_sample_withheld,
                sanitized_samples=samples,
            )
            self._signatures[pattern_hash] = updated
            return updated

        # New signature: enforce max 100 signatures cap
        if len(self._signatures) >= self.MAX_SIGNATURES:
            return None

        classification = (
            "APPROVED_DEBUG_ENVELOPE"
            if eval_result.is_approved_envelope
            else "UNCERTAIN_NON_CHAT"
        )
        samples = (
            [eval_result.sanitized_text]
            if not eval_result.uncertain and eval_result.sanitized_text
            else []
        )

        record = AnomalySignatureRecord(
            pattern_hash=pattern_hash,
            classification=classification,
            occurrence_count=1,
            first_seen_at=now_iso,
            last_seen_at=now_iso,
            privacy_sample_withheld=eval_result.uncertain,
            sanitized_samples=samples,
        )
        self._signatures[pattern_hash] = record
        return record

    def get_signatures(self) -> list[AnomalySignatureRecord]:
        """Return all tracked anomaly signature records."""
        return list(self._signatures.values())
