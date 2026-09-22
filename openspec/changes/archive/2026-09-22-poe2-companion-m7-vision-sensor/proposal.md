# Proposal

## Why

While client logs and game processes provide zone and level progression, derived stats (such as elemental resistances, unreserved life/mana, armour, and evasion) are only visible on-screen in the in-game character panel. To enable accurate survival risk detection and gear deficiency identification without game injection or memory inspection, the companion requires a read-only vision sensor that classifies screens, parses character panel attributes, enforces rate limits via a vision budget, and guarantees multi-capture verification accuracy before surfacing critical alerts.

## What Changes

- Implement a read-only screen classifier identifying screen types (`CHARACTER_PANEL`, `ITEM_TOOLTIP`, `SKILL_PANEL`, `PASSIVE_SCREEN_TARGETED`, and `UNKNOWN`).
- Implement a structured parser for visible derived character stats (life, mana, spirit, armour, evasion, fire/cold/lightning/chaos resistances).
- Enforce strict semantic verification states: multi-capture matching yields `VERIFIED`, single capture yields `SINGLE_SOURCE`, and out-of-range or mismatching captures yield `CONFLICTING`.
- Implement a rate-limiting vision budget manager that tracks hourly call ceilings, enforce minimum inter-capture intervals, and manages a size-capped screenshot cache.
- Implement explicit vision privacy disclosures declaring local vs cloud model modes and automatic redaction of non-pertinent screen areas.
- Add `companion vision status` and `companion vision parse-panel` CLI subcommands.

## Capabilities

### New Capabilities
- `vision-sensor`: Read-only visual sensing with screen classification, character panel parsing, multi-capture verification, vision budget enforcement, and privacy disclosure.

### Modified Capabilities
(None)

## Impact

- Creates `companion/vision/` module containing budget trackers, privacy guards, screen classifiers, parsers, and caching logic.
- Extends CLI with `companion vision` subcommands.
- Connects vision observation facts to the observation bus and character state store without any direct game memory reading or input automation.
