# Architectural Deep-Dive & System Health Analysis
**Document ID:** `ARCH-2026-10-01-DEEP-DIVE`  
**Date:** 2026-10-01  
**Project:** `poe2-companion` (Path of Exile 2 Companion & PoB2 Live Equipment Advisor)  
**Status:** DRAFT / RECORDED FOR CONTINUATION  

---

## 1. Executive Summary & Verdict Scorecard

### Overall Architectural Rating: `8.0 / 10` (Tier: Mature Specialized Desktop Companion)

| Dimension | Rating | Description & Current State |
| :--- | :---: | :--- |
| **Domain Logic & PoE2 Simulation** | **9.2 / 10** | **Superior.** Menggunakan official Lua VM Path of Building 2 secara langsung (bukan flat weight estimation atau heuristic math). Ground-truth DPS, EHP, dan ailment scaling akurat sesuai engine resmi game. |
| **Automated Testing & Regressions** | **9.5 / 10** | **Enterprise-Grade.** 1.841 unit/integration tests lulus deterministik dalam ~24–26 detik. Isolasi test fixture bersih, mencakup edge-cases dual-ring, weapon sets swap, dan movement speed penalty gates. |
| **State & Concurrency Management** | **6.5 / 10** | **Fragile / High Risk.** PoB2 session cache in-memory berbasis single process mutex lock (`_engine_lock`). Sesi Lua stateful rentan tercemar bila operasi `simulate_item` gagal di-restore secara transactional. |
| **Transport & I/O Architecture** | **6.5 / 10** | **Primitif.** Menggunakan Python standard library `ThreadingHTTPServer` dengan client-side polling agresif (clipboard poll setiap 600ms, status poll setiap 3000ms). Beban disk & thread konstan. |
| **Decision Pipeline Cohesion** | **7.5 / 10** | **Piped Heuristics.** Terdapat "Dual-Brain" antara `fubgun_priorities.py` (kebijakan build matematis) dan `tactical_advisor.py` (kebijakan taktis zona/sustain) yang belum disatukan dalam formal State Machine. |

---

## 2. Peta Arsitektur Saat Ini (System Topology)

```
[ IN-GAME PoE2 CLIENT ]
       │
       ├─ [Ctrl + C] ──────────────────────────┐
       │                                       │
       ▼                                       ▼
[ Windows Clipboard ]                 [ Client.txt / Log Tailer ]
       │                                       │
       │ (Polling 600ms via fetch)             │ (Tailer events)
       ▼                                       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND PRESENTATION LAYER                     │
│  - Single Page Application (dashboard/index.html, app.js, style.css)   │
│  - Dark Fantasy UI, Auto-stage resolver (getEffectiveStage)            │
│  - Real-time comparison card, Visual Badges (👑/🟢/🟡/🛑)             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP REST API (JSON)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        COMPANION SERVER & API LAYER                    │
│  - companion/dashboard_server.py (ThreadingHTTPServer)                 │
│  - companion/dashboard_api.py (normalize_char_id, router)              │
│  - In-Memory Cache: _GLOBAL_POB_SESSIONS (Key: Char Name)              │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
                    ▼                                ▼
┌───────────────────────────────────────┐ ┌──────────────────────────────┐
│       DECISION & TACTICAL BRAIN       │ │    PoB2 SIMULATION ENGINE    │
│  - fubgun_priorities.py (Core Policy) │ │  - pob2_equipment_advisor.py │
│  - tactical_advisor.py (Zone/Sustain) │ │  - pob_mcp Lua IPC Process   │
│  - zone_threats.py (Act Threat Matrix)│ │  - CombinedDPS / EHP Engine  │
│  - precedence.py & data_sufficiency.py│ │  - Mutex Lock: _engine_lock  │
└───────────────────┬───────────────────┘ └──────────────┬───────────────┘
                    │                                    │
                    └─────────────────┬──────────────────┘
                                      │
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          PERSISTENCE & RUNTIME                         │
│  - runtime/characters/<NAME>.json (Active Stage, Loadout, Tree)        │
│  - runtime/session.json (Current Zone, Log Offsets, Combat State)      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Analisis Mendalam Sub-Sistem (Deep Dive)

### A. PoB2 Engine Bridge (`companion/equipment/pob2_equipment_advisor.py`)
* **Kekuatan:**
  - Mengeliminasi tebak-tebakan kalkulasi game. Semua mod kompleks (seperti *14% increased Energy Shield*, *Adds 12 to 18 Phys*, *Crit Multi*) dihitung langsung oleh runtime Lua Path of Building 2 resmi.
  - Mendukung topologi slot kompleks: Dual-Ring (`Ring 1` vs `Ring 2` serialized Pareto evaluation) dan Dual Weapon Sets (`Weapon Set 1` vs `Weapon Set 2` Swap isolation).
* **Kelemahan & Titik Rentan:**
  - **Stateful Engine Mutation:** Setiap simulasi memanggil `engine.call("equip_item", ...)`. Jika engine mengalami exception sebelum baseline di-restore, build XML di memori Lua menjadi cacat/tercemar.
  - **Skill Context Dependency:** PoB2 mengkalkulasi stats pada `activeSkill` yang aktif. Bila karakter memiliki skill pasif/aura (seperti *Virtuous Barrier*) terpilih di XML baseline, flat damage serangan pada senjata/gloves bernilai 0 DPS. Wajib ada binding eksplisit ke `CROSSBOW_LEVELING` (Explosive Grenade).

### B. Decision Engine & Tactical Advisor (`fubgun_priorities.py`, `tactical_advisor.py`)
* **Kekuatan:**
  - Membaca konteks build nyata (Fubgun Flameblast Oil Grenade). Mengetahui bahwa pada level 15–32, granat crossbow bergantung 100% pada *flat attack damage* dari Senjata dan Gloves.
  - Membaca konteks zona (`zone_threats.py`): Mengenali bahwa Act 2 Vastiri Outskirts penuh dengan ancaman Fire Damage dari bandit dan rolling boulders, sehingga kehilangan Fire Resistance diklasifikasikan sebagai *Lethal*, sedangkan kehilangan Lightning Resistance ditoleransi jika DPS meningkat.
* **Kelemahan & Titik Rentan:**
  - **Dual-Brain Discrepancy:** `fubgun_priorities.py` mengembalikan enum `Verdict` matematis, lalu diteruskan ke `tactical_advisor.py` yang bisa meng-override vonis tersebut menjadi `REJECT` berdasarkan sustain (Life on Hit / Mana on Kill) atau ancaman bos zona. Belum ada kontrak formal State Machine terpadu.

### C. Server & Client Transport (`dashboard_server.py`, `dashboard/app.js`)
* **Kekuatan:**
  - Zero-dependency: Berjalan di atas Python standard library `http.server` tanpa memerlukan dependensi Node.js atau server external kompleks.
  - Auto-clipboard reading: Pemain cukup menekan `Ctrl + C` pada item di dalam game PoE2, dashboard langsung mengevaluasi secara otomatis tanpa perlu paste manual.
* **Kelemahan & Titik Rentan:**
  - **Polling Loop Overhead:** Polling HTTP setiap 600ms membuang siklus I/O CPU dan disk secara sia-sia saat pemain sedang eksplorasi atau idle.
  - **Single Mutex Contention:** Request polling clipboard dan status dashboard bersaing pada `_engine_lock` yang sama dengan tombol manual evaluate.

---

## 4. Pelajaran dari Insiden Bug Terakhir (Post-Mortem Insights)

### 1. Insiden "Maelström Paw" (Gloves Direkomendasikan Padahal Rugi DPS)
* **Gejala:** Dashboard menyuruh memakai *Maelström Paw* (Energy Shield + Lightning Res) dan melepas *Ghoul Talons* (Double Flat Attack Damage + Life + Sustain).
* **Akar Masalah:**
  1. Engine PoB2 mengevaluasi item tanpa mengunci active socket group ke *Explosive Grenade*. PoB2 membaca DPS skill default kosong (delta: 0 DPS).
  2. Sistem mengira kandidat memberikan free +8% Lightning Res dan +19 Life tanpa kehilangan DPS.
* **Solusi yang Diterapkan:**
  - Di `pob2_equipment_advisor.py`: Otomatis bind `set_main_skill` ke primary attack skill (`CROSSBOW_LEVELING`) dan restore baseline XML sebelum & sesudah simulasi.
  - Di `tactical_advisor.py` & `fubgun_priorities.py`: Tambah deteksi *flat attack damage* & sustain drop, kunci penolakan tegas `REJECT` (`🛑 TAHAN GEAR LAMA`).

### 2. Insiden "Hasil Compare Suka Berubah-ubah" (Flip-Flop Evaluation)
* **Gejala:** Membandingkan item yang sama kadang keluar `REJECT`, kadang keluar `CONDITIONAL UPGRADE`, dan angka DPS melompat-lompat.
* **Akar Masalah:**
  1. Case-sensitivity ID karakter: URL browser meminta `char_id=BOMSHAk` (k kecil), sedangkan session di memory terdaftar sebagai `BOMSHAK` (K besar). Akibatnya lookup miss dan sistem jatuh ke fallback heuristic (rumus estimasi dummy).
  2. Stage drift: File karakter mencatat `lvl 1-14`, sedangkan level karakter sudah 22 (Act 2).
* **Solusi yang Diterapkan:**
  - Tambah fungsi `normalize_char_id()` di `dashboard_server.py` dan `dashboard_api.py`.
  - Tambah helper `getEffectiveStage()` di `app.js` untuk auto-correct level 22 ke `lvl 15-32`.

---

## 5. Roadmap Evolusi Arsitektur (Next-Level Refactor)

Jika sistem ini ingin ditingkatkan dari *Tier A Companion* menuju *Tier S Enterprise Production Tool*, berikut 4 langkah refactor strategis:

### Tahap 1: Transactional Snapshotting pada PoB2 Engine (Prioritas: Tinggi)
* **Tujuan:** Menjamin kebal 100% dari baseline pollution.
* **Desain:** Alih-alih memutasi session tunggal yang sedang aktif (`equip_item` -> `calc` -> `import_build`), gunakan worker pool atau fork sandbox XML terisolasi secara transactional (Copy-on-Write).

### Tahap 2: Unifikasi Decision Pipeline (Prioritas: Sedang)
* **Tujuan:** Menghapus ambiguitas antara `fubgun_priorities` dan `tactical_advisor`.
* **Desain:** Bangun satu pipeline terpadu (`DecisionPipeline`) dengan rantai evaluasi terurut:
  `Raw Item Text` ➔ `Topology Gate` ➔ `Build Breaker Filter` ➔ `PoB2 Simulation (DPS/EHP)` ➔ `Zone/Threat Tactical Rules` ➔ `Final Immutable Verdict`.

### Tahap 3: Migrasi Transport ke Server-Sent Events (SSE) / WebSocket (Prioritas: Sedang)
* **Tujuan:** Zero latency saat `Ctrl + C` di game dan 0% CPU polling overhead.
* **Desain:** Server menjalankan watcher clipboard OS di thread background. Saat teks clipboard baru terdeteksi, server langsung mendorong (*push*) event JSON ke browser via SSE/WebSocket. Browser tidak perlu lagi melakukan polling `GET /api/clipboard-poll` setiap 600ms.

### Tahap 4: FastAPI / Asynchronous Server (Prioritas: Rendah / Jangka Panjang)
* **Tujuan:** Concurrency non-blocking dan performa tinggi bila digunakan untuk multiple characters atau multi-client.
* **Desain:** Ganti `http.server.ThreadingHTTPServer` stdlib dengan framework async modern (`FastAPI` / `Litestar` + `uvicorn`).

---

## 6. Status Snapshot Berkas Saat Ini

* **Git Commit Terakhir:** `3256cf6` (`feat: integrate PoB2 web dashboard with live zone-aware tactical equipment advisor`)
* **Test Suite:** 1.841 tests passing (0 failures, durasi ~24 detik).
* **Spesifikasi Kerja User:** Seluruh berkas di bawah `openspec/changes/poe2-companion-development-observation-mode/` tetap utuh dan terisolasi.
