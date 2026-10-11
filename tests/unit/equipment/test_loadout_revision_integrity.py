"""Tests for loadout revision integrity, fingerprinting, and baseline consistency.

Covers Required Test Matrix:
A. Draft enrichment
B. Finalize
C. Finalized UNKNOWN -> known
D. Finalized known -> different known
E. Finalized clear
F. Identical item no-op
G. Promote candidate (exactly once)
H. Fingerprint mismatch
I. Legacy baseline safety
J. Revision history snapshots
"""

from pathlib import Path
import pytest
from companion.state.provenance import VerificationState
from companion.equipment.baseline import (
    BaselineSource,
    CharacterFact,
    CharacterStatBaseline,
)
from companion.cli import main
from companion.equipment.baseline_cli import run_baseline_set
from companion.equipment.baseline_gate import (
    LEGACY_ANCHOR_REQUIRES_REBASELINE,
    check_baseline_consistency,
)
from companion.equipment.contribution import ItemContribution
from companion.equipment.reconciler import reconcile_baseline_after_swap
from companion.equipment.loadout import (
    EquippedLoadout,
    FinalizedLoadoutMutationError,
    compute_item_fingerprint,
    compute_loadout_fingerprint,
    is_item_decision_equal,
)
from companion.equipment.loadout_cli import (
    load_loadout,
    load_loadout_history,
    run_loadout_clear,
    run_loadout_finalize,
    run_loadout_promote_candidate,
    run_loadout_set_item,
    save_loadout,
)
from companion.equipment.loadout_promotion import promote_candidate_to_loadout
from companion.equipment.schema import (
    ItemCandidate,
    ModifierScope,
    NormalizedModifier,
    NormalizedModifierType,
    SlotConflictTopology,
    SlotOccupancy,
    SlotType,
    WeaponSetContext,
)


def make_test_item(
    name: str,
    slot: SlotType,
    fire_res: float = 0.0,
    lightning_res: float = 0.0,
    armour: int = 0,
    evasion: int = 0,
    level_req: int = 1,
) -> ItemCandidate:
    mods = []
    if fire_res > 0:
        mods.append(
            NormalizedModifier(
                modifier_type=NormalizedModifierType.FIRE_RESISTANCE,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=fire_res,
                raw_text=f"+{int(fire_res)}% to Fire Resistance",
            )
        )
    if lightning_res > 0:
        mods.append(
            NormalizedModifier(
                modifier_type=NormalizedModifierType.LIGHTNING_RESISTANCE,
                scope=ModifierScope.GLOBAL_CHARACTER_STAT,
                value=lightning_res,
                raw_text=f"+{int(lightning_res)}% to Lightning Resistance",
            )
        )
    return ItemCandidate(
        item_id=f"id_{name.lower().replace(' ', '_')}",
        name=name,
        base_type=name,
        slot=slot,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(
            occupied_slots=[slot],
            conflicting_slots=[slot],
            is_known=True,
        ),
        local_armour=armour,
        local_evasion=evasion,
        required_level=level_req,
        modifiers=mods,
    )


# ---------------------------------------------------------------------------
# Matrix A: Draft enrichment does not increment revision
# ---------------------------------------------------------------------------
def test_matrix_a_draft_enrichment():
    loadout = EquippedLoadout.create_draft(character_id="char_draft")
    ring = make_test_item("Blackheart", SlotType.RING_1, fire_res=15)

    assert loadout.is_finalized is False
    assert loadout.revision == 1
    assert SlotType.RING_1 in loadout.unknown_slots

    loadout.set_slot(SlotType.RING_1, ring)

    assert loadout.is_finalized is False
    assert loadout.revision == 1
    assert SlotType.RING_1 in loadout.known_slots
    assert loadout.get_slot(SlotType.RING_1).item.name == "Blackheart"


# ---------------------------------------------------------------------------
# Matrix B: Finalize establishes initial stable revision 1
# ---------------------------------------------------------------------------
def test_matrix_b_finalize():
    loadout = EquippedLoadout.create_draft(character_id="char_b")
    boots = make_test_item("Wanderlust", SlotType.BOOTS)
    loadout.set_slot(SlotType.BOOTS, boots)

    loadout.finalize(loadout_id="loadout_b")
    assert loadout.is_finalized is True
    assert loadout.revision == 1
    assert loadout.loadout_id == "loadout_b"
    assert SlotType.BOOTS in loadout.known_slots


# ---------------------------------------------------------------------------
# Domain protection: Direct mutation on finalized loadout raises error
# ---------------------------------------------------------------------------
def test_domain_bypass_prevention():
    loadout = EquippedLoadout.create_draft(character_id="char_dom")
    loadout.finalize()
    assert loadout.is_finalized is True

    ring = make_test_item("Blackheart", SlotType.RING_1)
    with pytest.raises(FinalizedLoadoutMutationError):
        loadout.set_slot(SlotType.RING_1, ring)

    with pytest.raises(FinalizedLoadoutMutationError):
        loadout.clear_slot(SlotType.BOOTS)


# ---------------------------------------------------------------------------
# Matrix C: Finalized UNKNOWN -> known increments revision to 2, baseline stale
# ---------------------------------------------------------------------------
def test_matrix_c_finalized_unknown_to_known(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "char_c"

    # Draft setup and finalize
    boots = make_test_item("Wanderlust", SlotType.BOOTS)
    run_loadout_set_item(runtime_dir, char_id, "boots", "Item Class: Boots\nRarity: Unique\nWanderlust\nWool Shoes\n--------\n")
    fin = run_loadout_finalize(runtime_dir, char_id)
    assert fin.revision == 1
    assert fin.is_finalized is True

    # Baseline anchored to revision 1 and fingerprint 1
    fp1 = fin.compute_fingerprint()
    baseline = CharacterStatBaseline.create_partial(
        baseline_id=f"base_{char_id}",
        character_id=char_id,
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=fp1,
        life=1200,
        fire_res=75,
    )
    # Consistent initially
    gate = check_baseline_consistency(baseline, fin.revision, fin.compute_fingerprint())
    assert gate.is_consistent is True

    # Mutate: set UNKNOWN ring1 -> Blackheart
    res = run_loadout_set_item(
        runtime_dir,
        char_id,
        "ring1",
        "Item Class: Rings\nRarity: Unique\nBlackheart\nIron Ring\n--------\nRequirements:\nLevel: 4\n--------\n+15% to Fire Resistance\n",
    )
    assert res.revision == 2
    assert res.is_finalized is True

    # Baseline still revision 1 -> inconsistent / STALE
    gate_after = check_baseline_consistency(baseline, res.revision, res.compute_fingerprint())
    assert gate_after.is_consistent is False
    assert gate_after.reconciled_baseline.life.verification == VerificationState.STALE

    # History snapshot of revision 1 is recoverable
    rev1_snap = load_loadout_history(runtime_dir, char_id, revision=1)
    assert rev1_snap is not None
    assert rev1_snap.revision == 1
    assert rev1_snap.get_slot(SlotType.RING_1) is None


# ---------------------------------------------------------------------------
# Matrix D: Finalized known -> different known increments revision to 3
# ---------------------------------------------------------------------------
def test_matrix_d_finalized_known_to_different_known(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "char_d"

    # Initial setup
    run_loadout_set_item(runtime_dir, char_id, "ring1", "Item Class: Rings\nRarity: Unique\nBlackheart\nIron Ring\n--------\n+15% to Fire Resistance\n")
    run_loadout_finalize(runtime_dir, char_id)

    # Revision 1 -> 2 (different ring)
    run_loadout_set_item(runtime_dir, char_id, "ring1", "Item Class: Rings\nRarity: Rare\nCorpse Band\nGold Ring\n--------\n+20% to Lightning Resistance\n")
    loadout = load_loadout(runtime_dir, char_id)
    assert loadout.revision == 2

    # Revision 2 -> 3 (another different ring)
    run_loadout_set_item(runtime_dir, char_id, "ring1", "Item Class: Rings\nRarity: Unique\nBerek's Grip\nTwo-Stone Ring\n--------\n+25% to Cold Resistance\n")
    loadout3 = load_loadout(runtime_dir, char_id)
    assert loadout3.revision == 3
    assert loadout3.get_slot(SlotType.RING_1).item.name == "Berek's Grip"


# ---------------------------------------------------------------------------
# Matrix E: Finalized clear increments revision to 4
# ---------------------------------------------------------------------------
def test_matrix_e_finalized_clear(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "char_e"

    run_loadout_set_item(runtime_dir, char_id, "ring1", "Item Class: Rings\nRarity: Unique\nBlackheart\nIron Ring\n--------\n+15% to Fire Resistance\n")
    run_loadout_finalize(runtime_dir, char_id)
    # rev 1 -> 2
    run_loadout_set_item(runtime_dir, char_id, "ring1", "Item Class: Rings\nRarity: Rare\nCorpse Band\nGold Ring\n--------\n+20% to Lightning Resistance\n")
    # rev 2 -> 3
    run_loadout_set_item(runtime_dir, char_id, "ring1", "Item Class: Rings\nRarity: Unique\nBerek's Grip\nTwo-Stone Ring\n--------\n+25% to Cold Resistance\n")
    l3 = load_loadout(runtime_dir, char_id)
    assert l3.revision == 3

    # Clear ring1 -> rev 4
    run_loadout_clear(runtime_dir, char_id, "ring1")
    l4 = load_loadout(runtime_dir, char_id)
    assert l4.revision == 4
    assert l4.get_slot(SlotType.RING_1) is None
    assert SlotType.RING_1 in l4.unknown_slots


# ---------------------------------------------------------------------------
# Matrix F: Identical item no-op does not increment revision or write history
# ---------------------------------------------------------------------------
def test_matrix_f_identical_item_noop(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "char_f"

    item_text = "Item Class: Rings\nRarity: Unique\nBlackheart\nIron Ring\n--------\n+15% to Fire Resistance\n"
    run_loadout_set_item(runtime_dir, char_id, "ring1", item_text)
    run_loadout_finalize(runtime_dir, char_id)
    l1 = load_loadout(runtime_dir, char_id)
    assert l1.revision == 1

    # Setting exact same representation into slot ring1
    run_loadout_set_item(runtime_dir, char_id, "ring1", item_text)
    l_after = load_loadout(runtime_dir, char_id)
    assert l_after.revision == 1

    # No history duplicate created for revision 1
    snap = load_loadout_history(runtime_dir, char_id, revision=1)
    assert snap is None


# ---------------------------------------------------------------------------
# Matrix G: Promote candidate increments revision exactly once
# ---------------------------------------------------------------------------
def test_matrix_g_promote_candidate_exactly_once(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "char_g"

    # Setup finalized loadout at revision 4
    run_loadout_set_item(runtime_dir, char_id, "boots", "Item Class: Boots\nRarity: Rare\nOld Boots\nMesh Boots\n--------\n")
    run_loadout_finalize(runtime_dir, char_id)
    # rev 1 -> 2
    run_loadout_set_item(runtime_dir, char_id, "boots", "Item Class: Boots\nRarity: Rare\nBoots V2\nMesh Boots\n--------\n")
    # rev 2 -> 3
    run_loadout_set_item(runtime_dir, char_id, "boots", "Item Class: Boots\nRarity: Rare\nBoots V3\nMesh Boots\n--------\n")
    # rev 3 -> 4
    run_loadout_set_item(runtime_dir, char_id, "boots", "Item Class: Boots\nRarity: Rare\nBoots V4\nMesh Boots\n--------\n")
    l4 = load_loadout(runtime_dir, char_id)
    assert l4.revision == 4

    candidate_text = "Item Class: Boots\nRarity: Rare\nNew Boots V5\nMesh Boots\n--------\n+30% to Fire Resistance\n"
    new_loadout, _ = run_loadout_promote_candidate(
        runtime_dir=runtime_dir,
        character_id=char_id,
        slot_name="boots",
        candidate_text=candidate_text,
    )
    assert new_loadout.revision == 5
    assert new_loadout.get_slot(SlotType.BOOTS).item.name == "New Boots V5"


# ---------------------------------------------------------------------------
# Matrix H: Fingerprint mismatch defense-in-depth catches content change
# ---------------------------------------------------------------------------
def test_matrix_h_fingerprint_mismatch():
    loadout = EquippedLoadout.create_draft(character_id="char_h")
    ring1 = make_test_item("Ring A", SlotType.RING_1, fire_res=10)
    loadout.set_slot(SlotType.RING_1, ring1)
    loadout.finalize()
    assert loadout.revision == 1

    fp_initial = loadout.compute_fingerprint()
    baseline = CharacterStatBaseline.create_partial(
        baseline_id="base_h",
        character_id="char_h",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=fp_initial,
        life=1000,
    )

    # Artificial isolated scenario: loadout content changed without revision bump
    ring2 = make_test_item("Ring B Modified", SlotType.RING_1, fire_res=40)
    loadout.shared_slots[SlotType.RING_1.value] = loadout.shared_slots[SlotType.RING_1.value].model_copy(
        update={"item": ring2}
    )
    fp_modified = loadout.compute_fingerprint()
    assert fp_modified != fp_initial

    # Baseline consistency fails because fingerprint differs even though revision is 1 == 1
    gate = check_baseline_consistency(baseline, current_loadout_revision=1, current_loadout_fingerprint=fp_modified)
    assert gate.is_consistent is False
    assert any("fingerprint" in notice.lower() for notice in gate.notices)


# ---------------------------------------------------------------------------
# Matrix I: Legacy baseline lacking fingerprint requires rebaseline
# ---------------------------------------------------------------------------
def test_matrix_i_legacy_baseline_safety():
    loadout = EquippedLoadout.create_draft(character_id="char_i")
    loadout.finalize()
    fp = loadout.compute_fingerprint()

    # Legacy baseline: anchored_loadout_fingerprint is None
    legacy_base = CharacterStatBaseline.create_partial(
        baseline_id="base_legacy",
        character_id="char_i",
        anchored_loadout_revision=1,
        anchored_loadout_fingerprint=None,
        life=1000,
    )
    assert legacy_base.anchored_loadout_fingerprint is None

    gate = check_baseline_consistency(legacy_base, current_loadout_revision=1, current_loadout_fingerprint=fp)
    assert gate.is_consistent is False
    assert any(LEGACY_ANCHOR_REQUIRES_REBASELINE in notice for notice in gate.notices)


# ---------------------------------------------------------------------------
# Matrix J: History snapshot recoverable and byte/semantic content corresponds
# ---------------------------------------------------------------------------
def test_matrix_j_history_recovery(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    char_id = "char_j"

    # Revision 1
    run_loadout_set_item(runtime_dir, char_id, "boots", "Item Class: Boots\nRarity: Rare\nBoots Rev1\nMesh Boots\n--------\n")
    run_loadout_finalize(runtime_dir, char_id)

    # Transition to revision 2
    run_loadout_set_item(runtime_dir, char_id, "boots", "Item Class: Boots\nRarity: Rare\nBoots Rev2\nMesh Boots\n--------\n")

    # Recover snapshot of revision 1
    rev1 = load_loadout_history(runtime_dir, char_id, revision=1)
    assert rev1 is not None
    assert rev1.revision == 1
    assert rev1.get_slot(SlotType.BOOTS).item.name == "Boots Rev1"

    # Current canonical loadout is revision 2
    current = load_loadout(runtime_dir, char_id)
    assert current.revision == 2
    assert current.get_slot(SlotType.BOOTS).item.name == "Boots Rev2"


def test_character_fact_conflicting_is_not_known():
    fact = CharacterFact[int](
        value=50,
        source=BaselineSource.MANUAL_USER_INPUT,
        observed_at="2026-09-25T00:00:00Z",
        verification=VerificationState.CONFLICTING,
    )
    assert fact.is_known is False


def test_movement_speed_reconciliation_promotion():
    base = CharacterStatBaseline.create_partial(
        baseline_id="b1",
        character_id="c1",
        anchored_loadout_revision=1,
        movement_speed=7,
    )
    disp = ItemContribution(
        item_id="i1",
        slot=SlotType.BOOTS,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(occupied_slots=[SlotType.BOOTS], conflicting_slots=[SlotType.BOOTS], is_known=True),
        movement_speed_delta=10.0,
    )
    cand = ItemContribution(
        item_id="i2",
        slot=SlotType.BOOTS,
        slot_occupancy=SlotOccupancy.SINGLE_SLOT,
        slot_conflict_topology=SlotConflictTopology(occupied_slots=[SlotType.BOOTS], conflicting_slots=[SlotType.BOOTS], is_known=True),
        movement_speed_delta=25.0,
    )
    reconciled = reconcile_baseline_after_swap(
        baseline=base,
        displaced_contributions=[disp],
        candidate_contribution=cand,
        new_loadout_revision=2,
    )
    assert reconciled.movement_speed.value == 22
    assert reconciled.movement_speed.source == BaselineSource.DERIVED_CALCULATION
    assert reconciled.movement_speed.verification == VerificationState.VERIFIED


def test_cli_promote_candidate_creates_history_snapshot(tmp_path: Path, capsys: pytest.CaptureFixture):
    runtime_dir = str(tmp_path / "runtime")
    char_id = "test_char_cli_promote"

    item1_text = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
Requirements:
Level: 45
--------
+66 to maximum Life
+28% to Lightning Resistance
"""
    item2_text = """Item Class: Boots
Rarity: Rare
Storm Tread
Furtive Boots
--------
Requirements:
Level: 45
--------
+80 to maximum Life
+35% to Fire Resistance
"""

    item1_file = tmp_path / "boots1.txt"
    item1_file.write_text(item1_text, encoding="utf-8")
    item2_file = tmp_path / "boots2.txt"
    item2_file.write_text(item2_text, encoding="utf-8")

    # 1. Setup finalized loadout rev 1
    code = main(["gear", "loadout", "set-clipboard", "--slot", "boots", "--file", str(item1_file), "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0
    code = main(["gear", "loadout", "finalize", "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0

    l1 = load_loadout(runtime_dir, char_id)
    assert l1.revision == 1
    assert l1.is_finalized is True

    # 2. Run CLI promote-candidate
    code = main(["gear", "loadout", "promote-candidate", "--slot", "boots", "--file", str(item2_file), "--runtime", runtime_dir, "--character-id", char_id])
    assert code == 0

    # 3. Verify rev 1 snapshot exists in runtime/loadout_history/{char_id}/rev_000001.json
    snap_file = Path(runtime_dir) / "loadout_history" / char_id / "rev_000001.json"
    assert snap_file.exists()
    snap = load_loadout_history(runtime_dir, char_id, 1)
    assert snap is not None
    assert snap.revision == 1
    assert snap.get_slot(SlotType.BOOTS).item.name == "Loath Trail"

    # 4. Verify current loadout is rev 2
    l2 = load_loadout(runtime_dir, char_id)
    assert l2.revision == 2
    assert l2.get_slot(SlotType.BOOTS).item.name == "Storm Tread"

    # 5. Verify no duplicate snapshot or double increment
    history_dir = Path(runtime_dir) / "loadout_history" / char_id
    snapshots = list(history_dir.glob("*.json"))
    assert len(snapshots) == 1
    assert snapshots[0].name == "rev_000001.json"

    # 6. Verify state-accurate stdout wording
    captured = capsys.readouterr()
    assert "Slot 'boots' updated." in captured.out
    assert "Loadout revision: 1 -> 2." in captured.out
    assert "Existing baseline is now stale and requires re-baseline." in captured.out
