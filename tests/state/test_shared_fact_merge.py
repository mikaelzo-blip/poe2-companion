"""A stale in-memory CharacterState (the log observer's) must not revert newer facts on disk."""
from companion.state.provenance import ProvenancedField
from companion.state.schema import CharacterState
from companion.state.store import CharacterStateStore

LATER = "2099-01-01T00:00:00+00:00"  # Windows clock ticks can give equal timestamps


def test_stale_copy_keeps_newer_disk_facts_and_its_own_newer_ones(tmp_path):
    store = CharacterStateStore(runtime_dir=tmp_path)
    stale = CharacterState.create_initial("P", "P")  # loaded early: DEFAULT_INIT attributes
    fresh = stale.model_copy(deep=True)
    fresh.attributes["strength"] = ProvenancedField[int].create(30, source="POB2_CALCULATION", observed_at=LATER)
    fresh.resources["spirit"] = ProvenancedField[int].create(30, source="POB2_CALCULATION", observed_at=LATER)
    store.save_character(fresh)

    stale.resistances["fire"] = ProvenancedField[int].create(38, source="USER_IN_GAME_SYNC", observed_at=LATER)  # newer than disk
    store.save_character(stale)
    saved = store.load_character("P")
    assert saved.attributes["strength"].value == 30 and saved.resources["spirit"].value == 30
    assert saved.resistances["fire"].value == 38
