# Audit Arsitektur: Equipment Workflow & Item Comparison Engine

**Target Subsystem**: `companion/equipment/` & PoB2 MCP Integration
**Tanggal Audit**: 2026-10-08
**Repositori**: `poe2-companion`
**Dokumen Pendukung**: `POE2_Hermes_Companion_Blueprint_v2.md`, `README.md`

---

## 1. Executive Summary

Audit ini mendokumentasikan analisis arsitektur end-to-end terhadap alur kerja (*workflow*), sistem komparasi item (*equipment comparison*), dan mesin optimasi pembentukan karakter terkuat di **PoE2 Companion**.

Sistem ini dirancang bukan sekadar sebagai kalkulator stat mentah, melainkan **Journey Director & Tactical Gear Advisor** yang mengintegrasikan simulasi matematis presisi tinggi (Path of Building 2), pemahaman mekanika sinergi build (Fubgun Flameblast / Oil Grenade), dan mitigasi ancaman zona pertarungan (*Zone & Boss Threat Intelligence*).

---

## 2. Arsitektur End-to-End Workflow

Alur kerja evaluasi item beroperasi melalui pipa 6-tahap modular dari pembacaan data hingga keputusan taktis:

```text
[In-Game PoE2] ──(Ctrl+C / Client.txt / GGG OAuth)──┐
                                                    ▼
[Telemetry & Sensing Engine] ───────────────────────┤
  ├─ clipboard.py / live_watcher.py (polling loop)  │
  ├─ zone_threats.py (Client.txt zone transitions)  │
  └─ WinRT OCR / poe_oauth.py (fallback sync)       │
                                                    ▼
[Ingestion & Normalizer] ───────────────────────────┤
  ├─ parser.py: Synthesize dashless OCR/clipboard    │
  ├─ slots.py: Map base archetype (Spear, Flail...) │
  └─ Compound cache key: raw_text::char::stage::zone│
                                                    ▼
[Simulation Engine: PoB2 MCP Bridge] ───────────────┤
  ├─ pob2_equipment_advisor.py (LuaJIT headless IPC)│
  ├─ Active skill context binding                   │
  └─ XML state rollback di block `finally`          │
                                                    ▼
[Progression Policy & Build Breaker] ───────────────┤
  ├─ fubgun_priorities.py (Leveling vs Endgame)     │
  └─ fubgun_rules.py (Detect early ignite, dll)     │
                                                    ▼
[Tactical Advisor & Veto Gate] ─────────────────────┤
  ├─ tactical_advisor.py: Zone lethality & boss mods│
  ├─ Attribute headroom check (Str/Dex/Int)         │
  └─ merge_verdicts(): Strict Veto-Only Contract    │
                                                    ▼
[Actionable Output] ────────────────────────────────┘
  └─ Web Dashboard / CLI: EQUIP_NOW | CONDITIONAL_UPGRADE | REJECT
```

---

## 3. Engine Komparasi Item: PoB2 Headless Simulation Bridge

Companion tidak mengandalkan estimasi heuristik kasar jika engine tersedia, melainkan mengeksekusi simulasi langsung di runtime C++/Lua Path of Building 2 melalui bridge MCP (Model Context Protocol).

### 3.1. Active Skill Context Binding
- **Masalah**: Pada PoB2, penghitungan flat attack damage (`Adds X to Y Physical/Cold/Lightning/Chaos Damage`) pada senjata, sarung tangan, atau perhiasan sepenuhnya bergantung pada socket group skill yang aktif.
- **Implementasi**: `Pob2EquipmentSession` secara eksplisit mengunci `set_main_skill` ke skill serangan leveling (`CROSSBOW_LEVELING` / Explosive Grenade). Jika tidak dikunci, PoB2 mengevaluasi skill default/non-serangan dan melaporkan `dps_delta = 0`, memicu false positive atau evaluasi slot ofensif secara keliru.

### 3.2. Transactional State Isolation (Rollback Proteksi)
- Simulasi `simulate_item(slot, candidate)` memutasi XML build di memori Lua.
- **Garansi Transaksional**: Baseline XML bersih wajib di-restore sebelum dan sesudah simulasi dalam blok `finally`.
- **Visibilitas Kegagalan**: Jika restorasi gagal, sesi ditandai tidak sehat (`is_healthy = False`), memaksa restart proses dan re-import XML bersih untuk mencegah kebocoran *phantom stats* yang mencemari komparasi berikutnya.

### 3.3. Multi-Slot Topology Resolution
- **Dual-Ring Pareto Evaluation**: Slot Ring 1 dan Ring 2 dievaluasi secara independen terhadap kandidat baru (`simulate_ring_candidate`). Algoritma memilih penggantian yang menghasilkan dominasi Pareto (kombinasi DPS dan EHP optimal tanpa merusak batas resistensi).
- **Dual Weapon Set Isolation**: Mendukung pemisahan Weapon Set 1 (Spellcaster: Flameblast Staff) dan Weapon Set 2 (Attack/Oil: Crossbow). Item tidak dievaluasi silang secara keliru ke set yang tidak kompatibel.

---

## 4. Matriks Evaluasi "Karakter Terkuat" (Multi-Dimensional Optimization)

Konsep karakter terkuat diformulasikan sebagai fungsi multi-dimensi seimbang, bukan sekadar angka DPS tertinggi:

$$\text{Verdict} = f(\Delta\text{DPS}, \Delta\text{EHP}, \Delta\text{Res}, \Delta\text{Def}, \text{Sustain}, \text{Attrs}, \text{Mechanics})$$

| Dimensi | Kriteria Evaluasi & Threshold | Dampak Terhadap Karakter |
| :--- | :--- | :--- |
| **Ofensif** | $\Delta\text{DPS} \ge 0$, Leveling Protection ($\Delta\text{DPS} \le -2.0 \rightarrow \text{VETO}$) | Mencegah slot ofensif (Gloves/Rings/Amulet) ditukar demi stat defensif minor. |
| **Defensif Decisive** | Net Res $\ge 0$, $\Delta\text{Life} \ge 0$, Composite Local Def $\ge 20$ | Menjamin upgrade defensif pada Body Armour/Helmet/Boots langsung diputuskan `EQUIP_NOW`. |
| **Sustain** | Life on Hit, Mana on Kill, Life Regen rate | Mempertahankan fluiditas bertarung saat campaign tanpa kehabisan resource. |
| **Atribut & Headroom** | Persyaratan Level, Str, Dex, Int terhadap baseline | Menolak item jika menyebabkan atribut turun di bawah syarat gem/gear aktif. |
| **Resistensi Absolut** | Penurunan pada resistensi yang sudah negatif $\rightarrow \text{VETO}$ | Menghindari kondisi fatal *one-shot* dari bos elemen/chaos di campaign & early map. |
| **Sinergi Mekanik** | Build-Breaker Safety Gate | Mencegah mod pengganggu mematikan interaksi skill utama. |

---

## 5. Build-Breaker & Mekanika Spesifik (Fubgun Flameblast / Oil Grenade)

Karakter terkuat dapat rusak instan jika mekanika build terganggu oleh modifier yang tidak diinginkan.

### 5.1. Pencegahan Early Ignite (Fatal Build-Breaker)
- **Mekanika**: Build mengandalkan Weapon Set 2 (Oil Grenade) untuk menyebarkan kolam minyak, lalu meledakkannya menggunakan Weapon Set 1 (Flameblast).
- **Bahaya Mod**: Jika item pada Set 2 (atau armor/jewelry bersama) memiliki modifier:
  - `Adds # to # Fire Damage to Attacks`
  - `Gain % of Physical Damage as Extra Fire Damage`
- **Konsekuensi**: Serangan Oil Grenade akan memicu status Ignite pada kontak pertama, membakar kolam minyak secara prematur dan menghancurkan damage window Flameblast.
- **Tindakan Companion**: `fubgun_rules.py` menandai modifier ini sebagai `VERIFIED_BUILD_BREAKER` dengan severity `BUILD_BREAKER`, otomatis memicu verdict `REJECT`.

### 5.2. Dead Mod Whitelisting
- Modifier tidak material saat campaign seperti *Reflects Physical Damage to Melee Attackers* (Thorns), Stun Recovery, Light Radius, dan Item Rarity di-whitelist dalam `RE_CAMPAIGN_NON_MATERIAL`.
- Hilangnya mod-mod ini pada kandidat baru tidak pernah memblokir rekomendasi upgrade.

---

## 6. Mesin Veto & Safety Gates: Tactical Advisor

Penggabungan evaluasi matematis kebijakan progres (`policy_verdict`) dan kondisi situasional karakter (`tactical_verdict`) diatur oleh kontrak kanonikal **Strict Veto-Only**:

```python
def merge_verdicts(policy_verdict: Any, tactical_verdict: Any) -> str:
    # Veto-Only: Tactical can veto down to REJECT, but cannot promote
```

### Matriks Penggabungan Verdict
- `Policy: EQUIP_NOW` + `Tactical: EQUIP_NOW` $\rightarrow$ **`EQUIP_NOW`**
- `Policy: EQUIP_NOW` + `Tactical: REJECT` $\rightarrow$ **`REJECT`** *(Tactical Veto)*
- `Policy: CONDITIONAL_UPGRADE` + `Tactical: REJECT` $\rightarrow$ **`REJECT`** *(Tactical Veto)*
- `Policy: CONDITIONAL_UPGRADE` + `Tactical: EQUIP_NOW` $\rightarrow$ **`CONDITIONAL_UPGRADE`** *(Tidak dipromosikan)*
- `Policy: REJECT` + `Tactical: EQUIP_NOW` $\rightarrow$ **`REJECT`** *(Policy tidak dapat dioverride)*

### Intelijen Ancaman Zona (*Zone Threats*)
- Mengetahui profil ancaman area dari `Client.txt` (contoh: bos area dengan physical spike ekstrem atau burst fire).
- Mengevaluasi hazard map modifier (contoh: "Area has patches of Ignited Ground") dan status kekebalan karakter (Thawing Charm) sebelum menyarankan perombakan gear.

---

## 7. Ketahanan & Higienitas Runtime (Edge Cases Mitigations)

1. **Dashless OCR / Clipboard Parsing**: Mendeteksi teks item tanpa pembatas `---` (sering terjadi pada clipboard screenshot / WinRT OCR) dan menyintesis section secara dinamis agar stat tidak terbaca nol.
2. **Zero-Backend IPC Fast-Probe**: Memeriksa named pipe Docker (`\\.\pipe\docker_engine`) dalam waktu <1ms sebelum kalkulasi. Jika Docker tidak aktif, sistem langsung jatuh ke mode heuristik tanpa membekukan thread selama 120 detik.
3. **Compound Cache Key Polling**: Cache clipboard menggunakan kunci gabungan `raw_text::char_id::stage::guide::zone`, memastikan perubahan zona atau karakter langsung memicu evaluasi ulang item.
4. **Windows-Safe Subprocess IPC Timeout**: Menggunakan daemon reader thread + thread-safe queue untuk komunikasi LuaJIT IPC, mencegah error `WinError 10038` pada pipe Windows.
