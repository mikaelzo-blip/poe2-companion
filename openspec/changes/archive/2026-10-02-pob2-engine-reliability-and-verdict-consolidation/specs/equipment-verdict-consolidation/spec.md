# Spec Delta

## Purpose

Standardizes equipment recommendation verdict consolidation across all slot evaluation paths using a single veto-only tactical merge contract.

## ADDED Requirements

### Requirement: Canonical verdict merge contract
The system SHALL provide a canonical `merge_verdicts(policy_verdict: str | Verdict, tactical_verdict: str | Verdict | None) -> Verdict` function that consolidates build progression policy verdicts with situational tactical advisor verdicts.

#### Scenario: Tactical vetoes upgrade policy with reject
- **WHEN** policy evaluates an item as `EQUIP_NOW` or `CONDITIONAL_UPGRADE` but tactical advisor determines a lethal defense drop, sustain regression, or zone mismatch yielding `REJECT`
- **THEN** `merge_verdicts` returns `Verdict.REJECT`

#### Scenario: Tactical upgrade recommendation does not override policy reject
- **WHEN** policy evaluates an item as `REJECT` (e.g. build breaker, stat deficit, wrong archetype) but tactical advisor evaluates it as `EQUIP_NOW` or `CONDITIONAL_UPGRADE`
- **THEN** `merge_verdicts` returns `Verdict.REJECT`

#### Scenario: Tactical non-reject preserves policy upgrade
- **WHEN** policy evaluates an item as `EQUIP_NOW` and tactical advisor evaluates as `EQUIP_NOW` or `CONDITIONAL_UPGRADE`
- **THEN** `merge_verdicts` returns `Verdict.EQUIP_NOW`

#### Scenario: Tactical non-reject preserves conditional upgrade
- **WHEN** policy evaluates an item as `CONDITIONAL_UPGRADE` and tactical advisor evaluates as `EQUIP_NOW` or `CONDITIONAL_UPGRADE`
- **THEN** `merge_verdicts` returns `Verdict.CONDITIONAL_UPGRADE`

#### Scenario: Tactical verdict is absent or None
- **WHEN** tactical advice is unavailable or `tactical_verdict` is `None`
- **THEN** `merge_verdicts` returns the unmodified policy verdict

### Requirement: Consistent verdict consolidation across all slot paths
The equipment evaluation endpoint (`evaluate_item_payload`) SHALL execute `merge_verdicts()` identically across all three equipment paths: weapons (including dual-sets and weapon swaps), rings (including dual-ring placement evaluation), and generic equipment slots (helmet, body armour, boots, gloves, belt, amulet). No path SHALL permit tactical advice to promote a non-`EQUIP_NOW` policy verdict to `EQUIP_NOW`.

#### Scenario: Generic slot preserves conditional policy verdict
- **WHEN** an armour candidate produces `CONDITIONAL_UPGRADE` from equipment policy and `EQUIP_NOW` from tactical advice
- **THEN** the API returns `verdict: "CONDITIONAL_UPGRADE"` rather than overriding with `EQUIP_NOW`

#### Scenario: Weapon path applies tactical veto
- **WHEN** a weapon candidate produces `EQUIP_NOW` from weapon policy but `REJECT` from tactical advice
- **THEN** the API returns `verdict: "REJECT"` and cites the tactical headline as the primary reason

#### Scenario: Ring path applies tactical veto
- **WHEN** a ring candidate produces `EQUIP_NOW` for a chosen ring slot but `REJECT` from tactical advice
- **THEN** the API returns `verdict: "REJECT"` and cites the tactical headline

### Requirement: Full 3x9 verdict matrix verification
The system SHALL verify via automated tests the complete 9-combination Cartesian product of (`EQUIP_NOW`, `CONDITIONAL_UPGRADE`, `REJECT`) across all three evaluation pathways (`weapon`, `ring`, and `generic_slot`).

#### Scenario: All 9 combinations tested on generic slots
- **WHEN** the test suite executes the generic slot verdict matrix test
- **THEN** all 9 combinations of (policy_verdict x tactical_verdict) produce the expected merged verdict according to veto-only rules

#### Scenario: All 9 combinations tested on weapon slot
- **WHEN** the test suite executes the weapon slot verdict matrix test
- **THEN** all 9 combinations produce identical merged verdict outcomes to the generic slot path

#### Scenario: All 9 combinations tested on ring slots
- **WHEN** the test suite executes the dual-ring slot verdict matrix test
- **THEN** all 9 combinations produce identical merged verdict outcomes to the weapon and generic slot paths
