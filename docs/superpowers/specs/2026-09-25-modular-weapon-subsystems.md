# Modular Weapon Subsystems Specification (Approach 1)

**Date:** 2026-09-25
**Scope:** PoB2 Live Equipment Weapon Advisor Architecture & Regression Suite
**Status:** Approved

---

## 1. Architectural Boundaries

1. **`FubgunWeaponProfileRouter` (BUILD-SPECIFIC)**
   - Lives outside generic PoB2 session (in `companion.equipment.fubgun_weapon_router`).
   - Responsibility: Candidate + Progression Stage $\to$
     - Validity for Fubgun weapon plan at current progression stage (pre-swap vs post-swap).
     - Target weapon set (`WEAPON_SET_1` vs `WEAPON_SET_2`).
     - Relevant skill context (`Flameblast` for Set 1 staff post-swap; `Oil Grenade` for Set 2 crossbow post-swap).
     - Build breaker gating (e.g. flat fire to attacks on crossbows breaks Oil Grenade; staff in Set 1 exempt).

2. **`WeaponTopologyResolver` (BUILD-AGNOSTIC)**
   - Lives in `companion.equipment.weapon_topology`.
   - Responsibility: Canonical equipment compatibility & topology only.
   - Canonical rules:
     - 1H vs 2H topology (2H occupies both hand slots in the target set).
     - Main hand vs off hand legality.
     - Bow + Quiver compatibility (Bows allow Quiver in off-hand; other 2H weapons do not).
     - Staff / Crossbow incompatible off-hand clearing.
     - Slot mapping per weapon set (Set 1: `Weapon 1`, `Weapon 2`; Set 2: `Weapon 1 Swap`, `Weapon 2 Swap`).
     - Replacing 2H with 1H leaves other hand slot empty (`None`), never inventing phantom offhands.
     - Build-agnostic invariant: Results never depend on Fubgun rules or character progression stage.

3. **`Pob2EquipmentSession` / Weapon Executor (MATHEMATICAL ONLY)**
   - Receives an explicit `WeaponSimulationContext`.
   - Mutates the PoB build atomically under `_engine_lock`.
   - Enforces same-baseline invariant: restores baseline XML before equip and in `finally`.
   - Computes mathematical deltas only (Life, Resistances, Defenses, DPS, EHP).
   - Strictly does NOT decide `EQUIP` vs `REJECT`.

4. **Fubgun Policy (FINAL DECISION LAYER)**
   - Evaluates mathematical deltas against Fubgun build priorities.
   - Emits structured recommendation and human-readable verdict.

5. **Ambiguous 1H Placement**
   - When a 1H candidate placement is ambiguous within the same target set, dual-simulates both placements (e.g. Slot 1 vs Slot 2) against the exact same baseline.
   - No arbitrary weighted score; reports both independent placement deltas and comparative trade-offs.

---

## 2. Core Data Models

### 2.1 `WeaponArchetype` (Enum)
- `TWO_HAND_STAFF`
- `TWO_HAND_CROSSBOW`
- `TWO_HAND_BOW`
- `TWO_HAND_OTHER`
- `ONE_HAND_WEAPON`
- `OFF_HAND_SHIELD`
- `OFF_HAND_FOCUS`
- `OFF_HAND_QUIVER`
- `UNKNOWN_WEAPON`

### 2.2 `WeaponTopologyPlan`
```python
class WeaponTopologyPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    target_set: WeaponSetContext
    target_slot: str                  # e.g. "Weapon 1", "Weapon 1 Swap"
    clear_slots: tuple[str, ...]      # e.g. ("Weapon 2",) if 2H displaces offhand
    displaced_slots: tuple[str, ...]  # slots being unequipped/replaced
    archetype: WeaponArchetype
    is_valid_pairing: bool = True
    invalidation_reason: str = ""
    is_ambiguous_placement: bool = False
    alternative_slots: tuple[str, ...] = ()
```

### 2.3 `WeaponSimulationContext`
```python
class WeaponSimulationContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    target_set: WeaponSetContext
    target_slot: str
    skill_context: str | None
    weapon_archetype: WeaponArchetype
    topology_plan: WeaponTopologyPlan
    build_stage: BuildProgressionStage
    candidate_id: int
    candidate_name: str
    raw_candidate: str
```

---

## 3. Required Regression Test Matrix (A through H)

- **Regression A**: Staff in Weapon Set 1 occupies `Weapon 1` and `Weapon 2`; replaces `Weapon 1` and clears `Weapon 2`, leaving Set 2 completely untouched.
- **Regression B**: Crossbow in Weapon Set 2 occupies `Weapon 1 Swap` and `Weapon 2 Swap`; clears offhand and prohibits Quivers; leaves Set 1 untouched.
- **Regression C**: Bow + Quiver compatibility: Bow allows Quiver in offhand; Crossbow does not allow Quiver.
- **Regression D**: 2H weapon displacing 1H + Shield: correctly clears offhand shield, subtracting offhand shield stats (no phantom offhand retained).
- **Regression E**: 1H weapon replacing 2H weapon: equips in target slot, leaves other hand empty, does NOT fabricate phantom offhand.
- **Regression F**: Weapon set isolation: Swapping Weapon Set 1 does not alter Weapon Set 2; swapping Set 2 does not alter Set 1.
- **Regression G**: Ambiguous 1H placement: dual-simulates within same target set against same baseline without arbitrary weighted winner.
- **Regression H (NEW)**: Build-agnostic topology: The topology resolver produces the exact same topological plan (slots occupied/cleared) for Staff, Crossbow, and Bow regardless of build stage or build profile.
