"""End-to-end integration test for Milestone 8 gear auto-analysis pipeline."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from companion.gear import (
    ConflictType,
    EquippedItem,
    ItemSlot,
    compare_candidate_upgrade,
    compare_equipped_against_target,
    compute_item_hash,
    detect_mechanic_conflicts,
    evaluate_gear_staleness,
    generate_investment_advice,
    load_gear_audit_state,
    record_slot_audit,
    verify_tooltip_stability,
)
from companion.observations.bus import ObservationBus
from companion.observations.schema import (
    ObservationEvent,
    ObservationEventType,
    ObservationSource,
)
from companion.state.provenance import VerificationState


TOOLTIP_HELMET = """
Rarity: Rare
Gale Crown
Iron Helmet
--------
Requires Level 42, 48 Str
--------
Sockets: S S
--------
+40 to Maximum Life
+20% to Fire Resistance
+15% to Cold Resistance
"""

TOOLTIP_BOOTS = """
Rarity: Rare
Storm Tread
Iron Greaves
--------
Requires Level 45, 52 Str
--------
+35 to Maximum Life
+25% to Cold Resistance
"""

CANDIDATE_BOOTS_UPGRADE = """
Rarity: Rare
Titan Stride
Vaal Greaves
--------
Requires Level 50, 75 Str
--------
+70 to Maximum Life
+30% to Fire Resistance
+30% to Cold Resistance
"""


def test_m8_gear_end_to_end_pipeline(tmp_path: Path) -> None:
    # 1. Multi-capture corroboration
    item, ver_state = verify_tooltip_stability([TOOLTIP_HELMET, TOOLTIP_HELMET], slot=ItemSlot.HELMET)
    assert item is not None
    assert ver_state == VerificationState.VERIFIED
    assert item.verification == VerificationState.VERIFIED

    # 2. Deterministic hashing
    hash1 = compute_item_hash(item)
    assert len(hash1) == 64
    assert hash1 == item.item_hash

    # 3. Record audit to storage and emit observation event
    bus = ObservationBus()
    received_events: list[ObservationEvent] = []
    bus.subscribe(ObservationEventType.STAT_OBSERVATION, lambda e: received_events.append(e))

    char_id = "test_merc"
    _, _, state1 = record_slot_audit(tmp_path, char_id, ItemSlot.HELMET, [TOOLTIP_HELMET, TOOLTIP_HELMET])
    assert ItemSlot.HELMET in state1.slots

    # Record boots slot
    _, _, state2 = record_slot_audit(tmp_path, char_id, ItemSlot.BOOTS, [TOOLTIP_BOOTS, TOOLTIP_BOOTS])
    assert ItemSlot.BOOTS in state2.slots

    # Publish observation event
    bus.publish(
        ObservationEvent.create(
            event_type=ObservationEventType.STAT_OBSERVATION,
            source=ObservationSource.MANUAL_CHECKPOINT,
            character_id=char_id,
            payload={"audited_slots": [s.value for s in state2.slots.keys()]},
        )
    )
    assert len(received_events) == 1
    assert "helmet" in received_events[0].payload["audited_slots"]

    # 4. Verify persistent reload across sessions
    reloaded = load_gear_audit_state(tmp_path, char_id)
    assert len(reloaded.slots) == 2
    assert reloaded.slots[ItemSlot.HELMET].base_type == "Iron Helmet"

    # 5. Check staleness TTL
    future_now = datetime.now(timezone.utc) + timedelta(hours=2)
    stale_state = evaluate_gear_staleness(reloaded.slots[ItemSlot.HELMET], now=future_now, ttl_minutes=60)
    assert stale_state == VerificationState.STALE

    # 6. Candidate upgrade comparison
    equipped_boots = reloaded.slots[ItemSlot.BOOTS]
    cand_boots, _ = verify_tooltip_stability([CANDIDATE_BOOTS_UPGRADE], slot=ItemSlot.BOOTS)
    assert cand_boots is not None

    upg = compare_candidate_upgrade(equipped_boots, cand_boots)
    assert upg.action == "UPGRADE"
    assert upg.score_delta > 0

    # 7. Mechanic conflict detection (attribute deficit)
    char_stats = {"str": 40, "dex": 50, "int": 50}
    conflicts = detect_mechanic_conflicts(equipped_boots, character_attributes=char_stats)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == ConflictType.UNMET_ATTRIBUTE
    assert "52 Str" in conflicts[0].description
