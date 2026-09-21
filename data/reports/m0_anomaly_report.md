# M0 Source Validation and Anomaly Report

- **Build Name**: Fubgun Flameblast Oil Grenade
- **Game Version**: 0.5.5
- **Tool Version**: 0.1.0
- **Execution Timestamp (UTC)**: 2026-09-21T17:38:02.116613+00:00

## Summary

- Total Snapshots: 9
- Status PASS: 3
- Status ANOMALIES: 6
- Status FAIL: 0

## Level Interval Shapes

- Range `[min, max]`: 380
- Unrestricted (omitted/None): 16
- Unresolved single uint: 0

## Weapon Set Distributions

- `DEFAULT_OR_SHARED`: 940 passive allocations
- `SPECIALISATION_1`: 149 passive allocations
- `SPECIALISATION_2`: 153 passive allocations
- `UNKNOWN_RESERVED`: 0 passive allocations
- `OTHER`: 0 passive allocations

## Cast on Dodge Meta-Gem Findings

- **lvl 52 Swap**: Symbol `Metadata/Items/Gems/SkillGemCastOnDodge`, Interval `[58, 100]` — *meta-gem unsupported by official planner*
- **lvl 53-68**: Symbol `Metadata/Items/Gems/SkillGemCastOnDodge`, Interval `[58, 100]` — *meta-gem unsupported by official planner*
- **lvl 85**: Symbol `Metadata/Items/Gems/SkillGemCastOnDodge`, Interval `[58, 100]` — *meta-gem unsupported by official planner*
- **Endgame**: Symbol `Metadata/Items/Gems/SkillGemCastOnDodge`, Interval `[58, 100]` — *meta-gem unsupported by official planner*
- **Mageblood**: Symbol `Metadata/Items/Gems/SkillGemCastOnDodge`, Interval `[58, 100]` — *meta-gem unsupported by official planner*
- **DoT Cap**: Symbol `Metadata/Items/Gems/SkillGemCastOnDodge`, Interval `[58, 100]` — *meta-gem unsupported by official planner*

## Dual Weapon-Set Passives

- **Mageblood**: Passive `dexterity30_` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **Mageblood**: Passive `dexterity13` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **Mageblood**: Passive `attributes7` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **Mageblood**: Passive `strength64` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **Mageblood**: Passive `attributes70` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **Mageblood**: Passive `strength48` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **Mageblood**: Passive `strength68` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **Mageblood**: Passive `area_attacks11` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **Mageblood**: Passive `area_attacks61` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **Mageblood**: Passive `attributes19` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **Mageblood**: Passive `attributes43` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **Mageblood**: Passive `dexterity65_` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **Mageblood**: Passive `ranged13` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **DoT Cap**: Passive `dexterity13` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **DoT Cap**: Passive `attributes7` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **DoT Cap**: Passive `projectiles47` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **DoT Cap**: Passive `attributes70` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **DoT Cap**: Passive `strength48` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **DoT Cap**: Passive `intelligence8` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **DoT Cap**: Passive `intelligence52` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **DoT Cap**: Passive `intelligence54` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **DoT Cap**: Passive `strength68` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1
- **DoT Cap**: Passive `area_attacks11` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_2
- **DoT Cap**: Passive `fire62` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1, SPECIALISATION_2
- **DoT Cap**: Passive `dexterity75` appears in contexts: DEFAULT_OR_SHARED, SPECIALISATION_1

## Additional Text & Planner Markup

- Total Non-Empty `additional_text` Entries: 105
- Recognized Official Planner Markup Entries: 0

## Raw Passive Duplicates

- Total Raw Duplicate Occurrences: 228
- Total Duplicated Raw Passive Entries: 228

| Stage | Passive ID | Context | Occurrences | Duplicate Count | Original Indices |
|---|---|---|---|---|---|
| lvl 1-14 | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [9, 21] |
| lvl 1-14 | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [10, 22] |
| lvl 1-14 | `strength36` | `DEFAULT_OR_SHARED` | 2 | 1 | [11, 23] |
| lvl 15-32 | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [9, 53] |
| lvl 15-32 | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 54] |
| lvl 15-32 | `strength36` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 55] |
| lvl 33-51 | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [9, 74] |
| lvl 33-51 | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 75] |
| lvl 33-51 | `strength36` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 76] |
| lvl 52 Swap | `dexterity26` | `DEFAULT_OR_SHARED` | 2 | 1 | [1, 99] |
| lvl 52 Swap | `dexterity27` | `DEFAULT_OR_SHARED` | 2 | 1 | [2, 100] |
| lvl 52 Swap | `dexterity28` | `DEFAULT_OR_SHARED` | 2 | 1 | [3, 101] |
| lvl 52 Swap | `dexterity29` | `DEFAULT_OR_SHARED` | 2 | 1 | [4, 102] |
| lvl 52 Swap | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [5, 96] |
| lvl 52 Swap | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [6, 97] |
| lvl 52 Swap | `strength82` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 103] |
| lvl 52 Swap | `dexterity79` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 104] |
| lvl 52 Swap | `strength81` | `DEFAULT_OR_SHARED` | 2 | 1 | [14, 105] |
| lvl 52 Swap | `dexterity77` | `DEFAULT_OR_SHARED` | 2 | 1 | [15, 106] |
| lvl 52 Swap | `attributes8_` | `DEFAULT_OR_SHARED` | 2 | 1 | [16, 107] |
| lvl 52 Swap | `dexterity76` | `DEFAULT_OR_SHARED` | 2 | 1 | [17, 108] |
| lvl 52 Swap | `dexterity75` | `DEFAULT_OR_SHARED` | 2 | 1 | [18, 109] |
| lvl 52 Swap | `attributes20-` | `DEFAULT_OR_SHARED` | 2 | 1 | [24, 110] |
| lvl 52 Swap | `attributes19` | `DEFAULT_OR_SHARED` | 2 | 1 | [25, 111] |
| lvl 52 Swap | `dexterity64` | `DEFAULT_OR_SHARED` | 2 | 1 | [26, 112] |
| lvl 52 Swap | `strength87` | `DEFAULT_OR_SHARED` | 2 | 1 | [27, 113] |
| lvl 52 Swap | `dexterity65_` | `DEFAULT_OR_SHARED` | 2 | 1 | [28, 114] |
| lvl 52 Swap | `attributes43` | `DEFAULT_OR_SHARED` | 2 | 1 | [29, 115] |
| lvl 52 Swap | `strength71` | `DEFAULT_OR_SHARED` | 2 | 1 | [35, 116] |
| lvl 52 Swap | `attributes6` | `DEFAULT_OR_SHARED` | 2 | 1 | [36, 117] |
| lvl 52 Swap | `strength70` | `DEFAULT_OR_SHARED` | 2 | 1 | [37, 118] |
| lvl 52 Swap | `strength69` | `DEFAULT_OR_SHARED` | 2 | 1 | [38, 119] |
| lvl 52 Swap | `attributes71` | `DEFAULT_OR_SHARED` | 2 | 1 | [39, 120] |
| lvl 52 Swap | `strength67` | `DEFAULT_OR_SHARED` | 2 | 1 | [40, 121] |
| lvl 52 Swap | `strength68` | `DEFAULT_OR_SHARED` | 2 | 1 | [41, 122] |
| lvl 53-68 | `dexterity26` | `DEFAULT_OR_SHARED` | 2 | 1 | [1, 128] |
| lvl 53-68 | `dexterity27` | `DEFAULT_OR_SHARED` | 2 | 1 | [2, 129] |
| lvl 53-68 | `dexterity28` | `DEFAULT_OR_SHARED` | 2 | 1 | [3, 130] |
| lvl 53-68 | `dexterity29` | `DEFAULT_OR_SHARED` | 2 | 1 | [4, 131] |
| lvl 53-68 | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [5, 125] |
| lvl 53-68 | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [6, 126] |
| lvl 53-68 | `strength82` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 132] |
| lvl 53-68 | `dexterity79` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 133] |
| lvl 53-68 | `strength81` | `DEFAULT_OR_SHARED` | 2 | 1 | [14, 134] |
| lvl 53-68 | `dexterity77` | `DEFAULT_OR_SHARED` | 2 | 1 | [15, 135] |
| lvl 53-68 | `attributes8_` | `DEFAULT_OR_SHARED` | 2 | 1 | [16, 136] |
| lvl 53-68 | `dexterity76` | `DEFAULT_OR_SHARED` | 2 | 1 | [17, 137] |
| lvl 53-68 | `dexterity75` | `DEFAULT_OR_SHARED` | 2 | 1 | [18, 138] |
| lvl 53-68 | `attributes20-` | `DEFAULT_OR_SHARED` | 2 | 1 | [24, 139] |
| lvl 53-68 | `attributes19` | `DEFAULT_OR_SHARED` | 2 | 1 | [25, 140] |
| lvl 53-68 | `dexterity64` | `DEFAULT_OR_SHARED` | 2 | 1 | [26, 141] |
| lvl 53-68 | `strength87` | `DEFAULT_OR_SHARED` | 2 | 1 | [27, 142] |
| lvl 53-68 | `dexterity65_` | `DEFAULT_OR_SHARED` | 2 | 1 | [28, 143] |
| lvl 53-68 | `attributes43` | `DEFAULT_OR_SHARED` | 2 | 1 | [29, 144] |
| lvl 53-68 | `strength71` | `DEFAULT_OR_SHARED` | 2 | 1 | [35, 145] |
| lvl 53-68 | `attributes6` | `DEFAULT_OR_SHARED` | 2 | 1 | [36, 146] |
| lvl 53-68 | `strength70` | `DEFAULT_OR_SHARED` | 2 | 1 | [37, 147] |
| lvl 53-68 | `strength69` | `DEFAULT_OR_SHARED` | 2 | 1 | [38, 148] |
| lvl 53-68 | `attributes71` | `DEFAULT_OR_SHARED` | 2 | 1 | [39, 149] |
| lvl 53-68 | `strength67` | `DEFAULT_OR_SHARED` | 2 | 1 | [40, 150] |
| lvl 53-68 | `strength68` | `DEFAULT_OR_SHARED` | 2 | 1 | [41, 151] |
| lvl 53-68 | `attributes5` | `DEFAULT_OR_SHARED` | 2 | 1 | [49, 152] |
| lvl 53-68 | `attributes70` | `DEFAULT_OR_SHARED` | 2 | 1 | [50, 153] |
| lvl 53-68 | `strength48` | `DEFAULT_OR_SHARED` | 2 | 1 | [52, 154] |
| lvl 85 | `dexterity26` | `DEFAULT_OR_SHARED` | 2 | 1 | [1, 145] |
| lvl 85 | `dexterity27` | `DEFAULT_OR_SHARED` | 2 | 1 | [2, 146] |
| lvl 85 | `dexterity28` | `DEFAULT_OR_SHARED` | 2 | 1 | [3, 147] |
| lvl 85 | `dexterity29` | `DEFAULT_OR_SHARED` | 2 | 1 | [4, 148] |
| lvl 85 | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [5, 142] |
| lvl 85 | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [6, 143] |
| lvl 85 | `strength82` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 149] |
| lvl 85 | `dexterity79` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 150] |
| lvl 85 | `strength81` | `DEFAULT_OR_SHARED` | 2 | 1 | [14, 151] |
| lvl 85 | `dexterity77` | `DEFAULT_OR_SHARED` | 2 | 1 | [15, 152] |
| lvl 85 | `attributes8_` | `DEFAULT_OR_SHARED` | 2 | 1 | [16, 153] |
| lvl 85 | `dexterity76` | `DEFAULT_OR_SHARED` | 2 | 1 | [17, 154] |
| lvl 85 | `dexterity75` | `DEFAULT_OR_SHARED` | 2 | 1 | [18, 155] |
| lvl 85 | `attributes20-` | `DEFAULT_OR_SHARED` | 2 | 1 | [24, 156] |
| lvl 85 | `attributes19` | `DEFAULT_OR_SHARED` | 2 | 1 | [25, 157] |
| lvl 85 | `dexterity64` | `DEFAULT_OR_SHARED` | 2 | 1 | [26, 158] |
| lvl 85 | `strength87` | `DEFAULT_OR_SHARED` | 2 | 1 | [27, 159] |
| lvl 85 | `dexterity65_` | `DEFAULT_OR_SHARED` | 2 | 1 | [28, 160] |
| lvl 85 | `attributes43` | `DEFAULT_OR_SHARED` | 2 | 1 | [29, 161] |
| lvl 85 | `strength71` | `DEFAULT_OR_SHARED` | 2 | 1 | [35, 162] |
| lvl 85 | `attributes6` | `DEFAULT_OR_SHARED` | 2 | 1 | [36, 163] |
| lvl 85 | `strength70` | `DEFAULT_OR_SHARED` | 2 | 1 | [37, 164] |
| lvl 85 | `strength69` | `DEFAULT_OR_SHARED` | 2 | 1 | [38, 165] |
| lvl 85 | `attributes71` | `DEFAULT_OR_SHARED` | 2 | 1 | [39, 166] |
| lvl 85 | `strength67` | `DEFAULT_OR_SHARED` | 2 | 1 | [40, 167] |
| lvl 85 | `strength68` | `DEFAULT_OR_SHARED` | 2 | 1 | [41, 168] |
| lvl 85 | `attributes5` | `DEFAULT_OR_SHARED` | 2 | 1 | [49, 169] |
| lvl 85 | `attributes70` | `DEFAULT_OR_SHARED` | 2 | 1 | [50, 170] |
| lvl 85 | `strength48` | `DEFAULT_OR_SHARED` | 2 | 1 | [74, 171] |
| lvl 85 | `strength47` | `DEFAULT_OR_SHARED` | 2 | 1 | [75, 176] |
| lvl 85 | `strength46` | `DEFAULT_OR_SHARED` | 2 | 1 | [76, 177] |
| lvl 85 | `attributes4` | `DEFAULT_OR_SHARED` | 2 | 1 | [77, 178] |
| lvl 85 | `intelligence8` | `DEFAULT_OR_SHARED` | 2 | 1 | [78, 179] |
| Endgame | `dexterity26` | `DEFAULT_OR_SHARED` | 2 | 1 | [1, 157] |
| Endgame | `dexterity27` | `DEFAULT_OR_SHARED` | 2 | 1 | [2, 158] |
| Endgame | `dexterity28` | `DEFAULT_OR_SHARED` | 2 | 1 | [3, 159] |
| Endgame | `dexterity29` | `DEFAULT_OR_SHARED` | 2 | 1 | [4, 160] |
| Endgame | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [5, 154] |
| Endgame | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [6, 155] |
| Endgame | `strength82` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 161] |
| Endgame | `dexterity79` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 162] |
| Endgame | `strength81` | `DEFAULT_OR_SHARED` | 2 | 1 | [14, 163] |
| Endgame | `dexterity77` | `DEFAULT_OR_SHARED` | 2 | 1 | [15, 164] |
| Endgame | `attributes8_` | `DEFAULT_OR_SHARED` | 2 | 1 | [16, 165] |
| Endgame | `dexterity76` | `DEFAULT_OR_SHARED` | 2 | 1 | [17, 166] |
| Endgame | `dexterity75` | `DEFAULT_OR_SHARED` | 2 | 1 | [18, 167] |
| Endgame | `attributes20-` | `DEFAULT_OR_SHARED` | 2 | 1 | [24, 168] |
| Endgame | `attributes19` | `DEFAULT_OR_SHARED` | 2 | 1 | [25, 169] |
| Endgame | `dexterity64` | `DEFAULT_OR_SHARED` | 2 | 1 | [26, 170] |
| Endgame | `strength87` | `DEFAULT_OR_SHARED` | 2 | 1 | [27, 171] |
| Endgame | `dexterity65_` | `DEFAULT_OR_SHARED` | 2 | 1 | [28, 172] |
| Endgame | `attributes43` | `DEFAULT_OR_SHARED` | 2 | 1 | [29, 173] |
| Endgame | `strength71` | `DEFAULT_OR_SHARED` | 2 | 1 | [35, 174] |
| Endgame | `attributes6` | `DEFAULT_OR_SHARED` | 2 | 1 | [36, 175] |
| Endgame | `strength70` | `DEFAULT_OR_SHARED` | 2 | 1 | [37, 176] |
| Endgame | `strength69` | `DEFAULT_OR_SHARED` | 2 | 1 | [38, 177] |
| Endgame | `attributes71` | `DEFAULT_OR_SHARED` | 2 | 1 | [39, 178] |
| Endgame | `strength67` | `DEFAULT_OR_SHARED` | 2 | 1 | [40, 179] |
| Endgame | `strength68` | `DEFAULT_OR_SHARED` | 2 | 1 | [41, 180] |
| Endgame | `attributes5` | `DEFAULT_OR_SHARED` | 2 | 1 | [49, 181] |
| Endgame | `attributes70` | `DEFAULT_OR_SHARED` | 2 | 1 | [50, 182] |
| Endgame | `strength48` | `DEFAULT_OR_SHARED` | 2 | 1 | [74, 183] |
| Endgame | `strength47` | `DEFAULT_OR_SHARED` | 2 | 1 | [75, 188] |
| Endgame | `strength46` | `DEFAULT_OR_SHARED` | 2 | 1 | [76, 189] |
| Endgame | `attributes4` | `DEFAULT_OR_SHARED` | 2 | 1 | [77, 190] |
| Endgame | `intelligence8` | `DEFAULT_OR_SHARED` | 2 | 1 | [78, 191] |
| Mageblood | `dexterity26` | `DEFAULT_OR_SHARED` | 2 | 1 | [1, 179] |
| Mageblood | `dexterity27` | `DEFAULT_OR_SHARED` | 2 | 1 | [2, 177] |
| Mageblood | `dexterity28` | `DEFAULT_OR_SHARED` | 2 | 1 | [3, 180] |
| Mageblood | `dexterity29` | `DEFAULT_OR_SHARED` | 2 | 1 | [4, 185] |
| Mageblood | `dexterity30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [5, 184] |
| Mageblood | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [6, 192] |
| Mageblood | `attributes30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [7, 201] |
| Mageblood | `dexterity13` | `DEFAULT_OR_SHARED` | 2 | 1 | [8, 208] |
| Mageblood | `strength82` | `DEFAULT_OR_SHARED` | 2 | 1 | [10, 207] |
| Mageblood | `dexterity79` | `DEFAULT_OR_SHARED` | 2 | 1 | [11, 168] |
| Mageblood | `strength81` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 165] |
| Mageblood | `strength83` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 167] |
| Mageblood | `attributes7` | `DEFAULT_OR_SHARED` | 2 | 1 | [14, 170] |
| Mageblood | `strength84` | `DEFAULT_OR_SHARED` | 2 | 1 | [15, 200] |
| Mageblood | `strength85` | `DEFAULT_OR_SHARED` | 2 | 1 | [16, 202] |
| Mageblood | `strength71` | `DEFAULT_OR_SHARED` | 2 | 1 | [18, 203] |
| Mageblood | `attributes6` | `DEFAULT_OR_SHARED` | 2 | 1 | [23, 198] |
| Mageblood | `strength70` | `DEFAULT_OR_SHARED` | 2 | 1 | [24, 206] |
| Mageblood | `strength69` | `DEFAULT_OR_SHARED` | 2 | 1 | [25, 191] |
| Mageblood | `attributes71` | `DEFAULT_OR_SHARED` | 2 | 1 | [26, 169] |
| Mageblood | `strength65_` | `DEFAULT_OR_SHARED` | 2 | 1 | [27, 188] |
| Mageblood | `strength64` | `DEFAULT_OR_SHARED` | 2 | 1 | [28, 197] |
| Mageblood | `attributes5` | `DEFAULT_OR_SHARED` | 2 | 1 | [29, 199] |
| Mageblood | `attributes70` | `DEFAULT_OR_SHARED` | 2 | 1 | [30, 190] |
| Mageblood | `strength48` | `DEFAULT_OR_SHARED` | 2 | 1 | [32, 174] |
| Mageblood | `strength47` | `DEFAULT_OR_SHARED` | 2 | 1 | [33, 205] |
| Mageblood | `strength46` | `DEFAULT_OR_SHARED` | 2 | 1 | [34, 196] |
| Mageblood | `attributes4` | `DEFAULT_OR_SHARED` | 2 | 1 | [35, 195] |
| Mageblood | `intelligence8` | `DEFAULT_OR_SHARED` | 2 | 1 | [36, 204] |
| Mageblood | `strength44` | `DEFAULT_OR_SHARED` | 2 | 1 | [37, 209] |
| Mageblood | `intelligence74` | `DEFAULT_OR_SHARED` | 2 | 1 | [38, 194] |
| Mageblood | `strength67` | `DEFAULT_OR_SHARED` | 2 | 1 | [47, 166] |
| Mageblood | `strength68` | `DEFAULT_OR_SHARED` | 2 | 1 | [48, 175] |
| Mageblood | `attributes72` | `DEFAULT_OR_SHARED` | 2 | 1 | [54, 171] |
| Mageblood | `dexterity77` | `DEFAULT_OR_SHARED` | 2 | 1 | [67, 173] |
| Mageblood | `attributes8_` | `DEFAULT_OR_SHARED` | 2 | 1 | [68, 176] |
| Mageblood | `dexterity76` | `DEFAULT_OR_SHARED` | 2 | 1 | [74, 178] |
| Mageblood | `dexterity75` | `DEFAULT_OR_SHARED` | 2 | 1 | [75, 182] |
| Mageblood | `attributes20-` | `DEFAULT_OR_SHARED` | 2 | 1 | [77, 186] |
| Mageblood | `attributes19` | `DEFAULT_OR_SHARED` | 2 | 1 | [78, 183] |
| Mageblood | `dexterity64` | `DEFAULT_OR_SHARED` | 2 | 1 | [79, 193] |
| Mageblood | `attributes43` | `DEFAULT_OR_SHARED` | 2 | 1 | [80, 189] |
| Mageblood | `strength87` | `DEFAULT_OR_SHARED` | 2 | 1 | [81, 181] |
| Mageblood | `dexterity65_` | `DEFAULT_OR_SHARED` | 2 | 1 | [82, 187] |
| Mageblood | `dexterity80` | `DEFAULT_OR_SHARED` | 2 | 1 | [86, 172] |
| DoT Cap | `strength34` | `DEFAULT_OR_SHARED` | 2 | 1 | [1, 177] |
| DoT Cap | `strength33_` | `DEFAULT_OR_SHARED` | 2 | 1 | [2, 191] |
| DoT Cap | `strength32` | `DEFAULT_OR_SHARED` | 2 | 1 | [3, 186] |
| DoT Cap | `strength35` | `DEFAULT_OR_SHARED` | 2 | 1 | [4, 174] |
| DoT Cap | `strength36` | `DEFAULT_OR_SHARED` | 2 | 1 | [5, 202] |
| DoT Cap | `strength37` | `DEFAULT_OR_SHARED` | 2 | 1 | [6, 219] |
| DoT Cap | `attributes30_` | `DEFAULT_OR_SHARED` | 2 | 1 | [7, 211] |
| DoT Cap | `dexterity13` | `DEFAULT_OR_SHARED` | 2 | 1 | [8, 197] |
| DoT Cap | `strength82` | `DEFAULT_OR_SHARED` | 2 | 1 | [10, 181] |
| DoT Cap | `dexterity79` | `DEFAULT_OR_SHARED` | 2 | 1 | [11, 179] |
| DoT Cap | `strength81` | `DEFAULT_OR_SHARED` | 2 | 1 | [12, 168] |
| DoT Cap | `strength83` | `DEFAULT_OR_SHARED` | 2 | 1 | [13, 180] |
| DoT Cap | `attributes7` | `DEFAULT_OR_SHARED` | 2 | 1 | [14, 172] |
| DoT Cap | `strength84` | `DEFAULT_OR_SHARED` | 2 | 1 | [15, 220] |
| DoT Cap | `strength85` | `DEFAULT_OR_SHARED` | 2 | 1 | [19, 201] |
| DoT Cap | `strength71` | `DEFAULT_OR_SHARED` | 2 | 1 | [21, 189] |
| DoT Cap | `attributes6` | `DEFAULT_OR_SHARED` | 2 | 1 | [26, 192] |
| DoT Cap | `strength70` | `DEFAULT_OR_SHARED` | 2 | 1 | [27, 194] |
| DoT Cap | `strength69` | `DEFAULT_OR_SHARED` | 2 | 1 | [28, 199] |
| DoT Cap | `attributes71` | `DEFAULT_OR_SHARED` | 2 | 1 | [29, 213] |
| DoT Cap | `strength65_` | `DEFAULT_OR_SHARED` | 2 | 1 | [30, 217] |
| DoT Cap | `strength64` | `DEFAULT_OR_SHARED` | 2 | 1 | [34, 200] |
| DoT Cap | `attributes5` | `DEFAULT_OR_SHARED` | 2 | 1 | [35, 218] |
| DoT Cap | `attributes70` | `DEFAULT_OR_SHARED` | 2 | 1 | [36, 193] |
| DoT Cap | `strength48` | `DEFAULT_OR_SHARED` | 2 | 1 | [38, 176] |
| DoT Cap | `strength47` | `DEFAULT_OR_SHARED` | 2 | 1 | [39, 207] |
| DoT Cap | `strength46` | `DEFAULT_OR_SHARED` | 2 | 1 | [40, 204] |
| DoT Cap | `attributes4` | `DEFAULT_OR_SHARED` | 2 | 1 | [41, 205] |
| DoT Cap | `intelligence8` | `DEFAULT_OR_SHARED` | 2 | 1 | [42, 210] |
| DoT Cap | `intelligence72` | `DEFAULT_OR_SHARED` | 2 | 1 | [43, 187] |
| DoT Cap | `attributes3` | `DEFAULT_OR_SHARED` | 2 | 1 | [44, 195] |
| DoT Cap | `intelligence71` | `DEFAULT_OR_SHARED` | 2 | 1 | [45, 215] |
| DoT Cap | `intelligence41__` | `DEFAULT_OR_SHARED` | 2 | 1 | [46, 198] |
| DoT Cap | `intelligence51` | `DEFAULT_OR_SHARED` | 2 | 1 | [48, 212] |
| DoT Cap | `intelligence52` | `DEFAULT_OR_SHARED` | 2 | 1 | [49, 209] |
| DoT Cap | `intelligence53_` | `DEFAULT_OR_SHARED` | 2 | 1 | [50, 214] |
| DoT Cap | `intelligence54` | `DEFAULT_OR_SHARED` | 2 | 1 | [51, 208] |
| DoT Cap | `intelligence45` | `DEFAULT_OR_SHARED` | 2 | 1 | [52, 216] |
| DoT Cap | `intelligence58` | `DEFAULT_OR_SHARED` | 2 | 1 | [53, 183] |
| DoT Cap | `intelligence59` | `DEFAULT_OR_SHARED` | 2 | 1 | [54, 178] |
| DoT Cap | `intelligence60` | `DEFAULT_OR_SHARED` | 2 | 1 | [55, 173] |
| DoT Cap | `attributes1` | `DEFAULT_OR_SHARED` | 2 | 1 | [56, 170] |
| DoT Cap | `intelligence56` | `DEFAULT_OR_SHARED` | 2 | 1 | [58, 203] |
| DoT Cap | `intelligence57` | `DEFAULT_OR_SHARED` | 2 | 1 | [59, 171] |
| DoT Cap | `strength44` | `DEFAULT_OR_SHARED` | 2 | 1 | [61, 206] |
| DoT Cap | `intelligence74` | `DEFAULT_OR_SHARED` | 2 | 1 | [62, 196] |
| DoT Cap | `strength67` | `DEFAULT_OR_SHARED` | 2 | 1 | [70, 175] |
| DoT Cap | `strength68` | `DEFAULT_OR_SHARED` | 2 | 1 | [71, 184] |
| DoT Cap | `attributes72` | `DEFAULT_OR_SHARED` | 2 | 1 | [76, 169] |
| DoT Cap | `dexterity77` | `DEFAULT_OR_SHARED` | 2 | 1 | [91, 182] |
| DoT Cap | `attributes8_` | `DEFAULT_OR_SHARED` | 2 | 1 | [92, 190] |
| DoT Cap | `dexterity76` | `DEFAULT_OR_SHARED` | 2 | 1 | [94, 188] |
| DoT Cap | `dexterity75` | `DEFAULT_OR_SHARED` | 2 | 1 | [95, 185] |

## Snapshots Detail

| Stage | Status | SHA-256 | Size (bytes) | Anomalies | Warnings |
|---|---|---|---|---|---|
| lvl 1-14 | `PASS` | `6dd123f803d4...` | 3082 | None | None |
| lvl 15-32 | `PASS` | `b8a1ed44fdde...` | 4162 | None | None |
| lvl 33-51 | `PASS` | `df4801480831...` | 4553 | None | None |
| lvl 52 Swap | `ANOMALIES` | `42743e97bbf9...` | 7291 | Metadata/Items/Gems/SkillGemCastOnDodge | None |
| lvl 53-68 | `ANOMALIES` | `a50eb7728cb6...` | 8718 | Metadata/Items/Gems/SkillGemCastOnDodge | None |
| lvl 85 | `ANOMALIES` | `66570ab58063...` | 10303 | Metadata/Items/Gems/SkillGemCastOnDodge | None |
| Endgame | `ANOMALIES` | `e58427e9b5ba...` | 10558 | Metadata/Items/Gems/SkillGemCastOnDodge | None |
| Mageblood | `ANOMALIES` | `88abcb1ecb4d...` | 13934 | Metadata/Items/Gems/SkillGemCastOnDodge | None |
| DoT Cap | `ANOMALIES` | `528d5bb9a9b1...` | 13952 | Metadata/Items/Gems/SkillGemCastOnDodge | None |
