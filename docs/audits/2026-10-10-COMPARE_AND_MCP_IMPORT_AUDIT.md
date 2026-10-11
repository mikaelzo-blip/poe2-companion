# Audit Mendalam: Compare Item & Auto-Import Data dari PoB2 MCP

**Tanggal**: 2026-10-10
**Cakupan**: alur compare item (dashboard → `dashboard_api` → PoB2 session / heuristic engine → policy → tactical veto → UI) dan alur import data karakter dari `path-of-building-2-mcp` (OAuth GGG, `import_character`, loadout/baseline lokal).
**Metode**: baca kode end-to-end, cek data nyata di `runtime/`, dan probe skrip terhadap kode saat ini. Setiap temuan diberi status **Terbukti** (direproduksi atau terlihat langsung di data/kode) atau **Kemungkinan besar** (logika kode jelas, tapi perlu verifikasi live dengan engine PoB2).

Catatan: audit sebelumnya (`EQUIPMENT_WORKFLOW_COMPARISON_AUDIT.md`) mendeskripsikan desain. Beberapa klaimnya tidak berlaku di kode saat ini. Contohnya: "Build-Breaker otomatis memicu REJECT" dan "Strict Veto-Only Contract" (lihat temuan 1 dan 2).

---

## Ringkasan

| # | Temuan | Severity | Status |
|---|---|---|---|
| 1 | Build-breaker (early ignite Oil Grenade) tidak pernah dicek di jalur PoB2 untuk slot non-senjata | Kritis | Terbukti |
| 2 | Jalur heuristic: tactical advice **mempromosikan** verdict engine, sehingga REJECT build-breaker berubah jadi EQUIP_NOW | Kritis | Terbukti |
| 3 | Sesi PoB2 bocor: invalidate tidak menutup engine, dan init yang gagal juga tidak menutupnya. Akibatnya container Docker yatim menumpuk | Tinggi | Terbukti (kode) -> **Diperbaiki** (b91fc8c) |
| 4 | Item "current" hasil import GGG kehilangan base properties, requirements, dan sebagian mod, sehingga perbandingan tidak setara | Tinggi | Terbukti (data runtime) -> **Sebagian diperbaiki** (teks GGG: 390dde7, 4d9af45; teks PoB2 -> clipboard: fix wave final review, hanya unit test) |
| 5 | Compare manual selalu mengirim `slot`, sehingga router senjata Fubgun dilewati. Di jalur auto-scan, UI menimpa slot pilihan server | Tinggi | Terbukti (kode) |
| 6 | Cabang senjata 1H ambigu selalu crash (`advice.rec1` tidak ada) dan memakai kalimat sebagai verdict | Tinggi | Terbukti |
| 7 | Simulasi slot Weapon Set 2 eksplisit tidak mengaktifkan weapon set 2 di PoB | Tinggi | Kemungkinan besar |
| 8 | Simulasi ring dan 1H tidak mengunci main skill; baseline ring dari sumber yang berbeda | Sedang | Terbukti (kode) |
| 9 | Baseline PoB2 basi: tidak di-refresh setelah ganti gear/naik level; level sesi menimpa level file sehingga stage salah | Sedang | Terbukti (kode) -> **Diperbaiki, unit test saja** (fba254f, 29b1995) |
| 10 | Threshold DPS/EHP absolut (tidak relatif); DPS absolut ditampilkan sebagai "%" | Sedang | Terbukti |
| 11 | Auto-pasang ke slot kosong mengabaikan verdict (REJECT pun dipasang dan dimasukkan ke baseline PoB2) | Sedang | Terbukti (kode) |
| 12 | Import GGG: baseline selalu kosong, nilai lama tidak pernah diperbarui, slot yang sudah dilepas tetap ada (ghost item) | Sedang | Terbukti -> **Sebagian diperbaiki** (17246e2, bf0dbb7, 0b4cbe9; default kelas 'Mercenary' tidak diubah) |
| 13 | Daftar karakter akun dibaca dari `oauth_status.json` yang tidak berisi karakter; fallback-nya data palsu | Sedang | Terbukti -> **Diperbaiki, unit test saja** (cbe3e49, 1b4c677) |
| 14 | `fetch_public_profile` menelan error OAuth lalu jatuh ke endpoint lama yang pasti gagal untuk PoE2, dengan pesan menyesatkan | Sedang | Terbukti (kode) -> **Diperbaiki, unit test saja** (cbe3e49) |
| 15 | Aturan build-breaker Fubgun diterapkan ke guide lain (Navira / generic) | Sedang | Terbukti (kode) |
| 16 | Counter staleness dipakai bersama antara compare manual dan auto-scan, sehingga simulasi bisa dibuang diam-diam | Rendah | Terbukti (kode) |
| 17 | Engine heuristic tidak punya model offense; `weapon_projection.py` adalah dead code | Rendah | Terbukti |
| 18 | Deteksi slot di UI: kelas "Staves/Quarterstaves" non-rare tidak terdeteksi | Rendah | Terbukti (kode) |

---

## 1. Build-breaker tidak dicek di jalur PoB2 (Kritis)

**Lokasi**: [dashboard_api.py:660](../../companion/dashboard_api.py) (`_pob2_other`), `_pob2_ring`, `_pob2_generic_weapon`.

Safety gate `evaluate_candidate_build_safety` (aturan `FubgunOilGrenadeFireRule` di [fubgun_rules.py](../../companion/equipment/fubgun_rules.py)) hanya dipanggil di dua tempat:
- engine heuristic ([engine.py:100](../../companion/equipment/engine.py)), dan
- router senjata Fubgun ([fubgun_weapon_router.py:184](../../companion/equipment/fubgun_weapon_router.py)).

Jalur PoB2 untuk armour, jewellery, dan ring hanya menjalankan `evaluate_fubgun_equipment_policy(delta)` (angka delta) dan tactical advice. Mod seperti `Adds X to Y Fire damage to Attacks` pada gloves/ring/amulet menaikkan DPS di PoB2, sehingga direkomendasikan EQUIP_NOW. Padahal ini adalah build-breaker yang didokumentasikan sebagai fatal setelah swap (lvl 52+).

**Probe** (gloves dengan `Adds 12 to 22 Fire damage to Attacks`, stage `lvl 53-68`, sesi PoB2 mock dengan delta positif):

```
ENGINE   : Verdict.REJECT | Build Breaker triggered: Harmful added Fire damage modifier ...
POB2     : pob2 EQUIP_NOW | Fubgun LEVELING_53_68 — Gloves: Life and Resistance upgrade; PoB2 confirms ...
```

**Perbaikan**: jalankan `evaluate_candidate_build_safety` di `_evaluate_item_payload_impl` **sebelum** memilih cabang, untuk semua engine. Jika hasilnya `VERIFIED_BUILD_BREAKER`, verdict akhir REJECT, sebagai hard veto setara dengan `merge_verdicts`.

## 2. Tactical mempromosikan verdict di jalur heuristic (Kritis)

**Lokasi**: [dashboard_api.py:802](../../companion/dashboard_api.py) (`_evaluate_heuristic`).

```python
elif tac_v == "EQUIP_NOW":
    out["verdict"] = "EQUIP_NOW"
```

Ini melanggar kontrak veto-only di `merge_verdicts` ("tactical tidak boleh mempromosikan"). Tactical dihitung ulang dari delta stat (`PobEquipmentDelta` sintetis) dan tidak melihat build-breaker. Akibatnya REJECT dari engine (termasuk build-breaker) ditimpa menjadi EQUIP_NOW. Probe yang sama:

```
ENGINE   : Verdict.REJECT | Build Breaker triggered ...
TACTICAL : Verdict.EQUIP_NOW
HEURISTIC: heuristic EQUIP_NOW | Doom Grip LEBIH BAGUS! Pasang sekarang ...
```

Cabang `CONDITIONAL_UPGRADE` dari `INSUFFICIENT_DATA` juga merupakan promosi.

**Perbaikan**: ganti blok override dengan `merge_verdicts(rec.verdict, tactical.verdict)`. Jika promosi INSUFFICIENT_DATA ke CONDITIONAL memang diinginkan, jadikan itu aturan eksplisit di satu tempat dan jangan pernah lewati REJECT.

## 3. Kebocoran sesi / container Docker PoB2 (Tinggi)

> **Diperbaiki** pada `b91fc8c`: engine ditutup saat init gagal; sesi dipertahankan saat invalidate. Pembuatan sesi serentak (race saat init lambat, penyebab container yatim yang tersisa) ditutup di fix wave final review dengan lock per karakter. Belum diverifikasi ulang live setelah lock itu.

**Lokasi**: [dashboard_server.py:82](../../companion/dashboard_server.py) (`invalidate_pob_session`), [pob2_equipment_advisor.py:451](../../companion/equipment/pob2_equipment_advisor.py).

- `invalidate_pob_session` melakukan `pop` sesi dari cache, menjalankan `sess.sync_character()` (fetch GGG + import, blocking di thread request), lalu **membuang** sesi tanpa `close()`. Hasil sync tidak terpakai, dan dua proses `docker run --rm -i` (engine + sandbox) tetap hidup tanpa pemilik.
- Dipicu oleh import JSON, update stats, fetch profile, dan pilih karakter. Setiap kejadian membocorkan 2 container.
- `initialize()`: jika `import_character` gagal setelah kedua engine start, engine tidak ditutup. `/api/evaluate-item` memakai `force_retry=True`, jadi setiap klik evaluate saat import gagal bisa membocorkan 2 container lagi.
- Sesi yang di-cache dengan `is_available=False` di `get_or_create_pob_session` juga diganti tanpa `close()`.

**Perbaikan**: pilih salah satu. (a) `invalidate` cukup memanggil `sess.sync_character()` dan tetap menyimpan sesi, atau (b) `pop` lalu `sess.close()`. Di `initialize()`, panggil `self.close()` pada jalur gagal setelah engine dibuat.

## 4. Item "current" hasil import tidak setara dengan kandidat (Tinggi)

> **Sebagian diperbaiki**: teks item GGG lengkap (properti, requirements, item level, Item Class) pada `390dde7, 4d9af45`; terverifikasi live pada 10 slot BOMSHAK. Teks PoB2 (`get_equipped`) memakai format internal PoB (tanpa Item Class, awalan `{tags:...}`, `Implicits: N`) dan sebelumnya ditolak parser, jadi `raw_text` PoB2 tidak pernah masuk ke runtime. Fix wave final review menambah `pob_item_to_clipboard` (`companion/equipment/pob_item_text.py`) dan menerapkannya saat sync; hanya diuji dengan unit test memakai fixture dari engine (`tests/fixtures/pob/`), belum diverifikasi live. Item PoB2 dengan mod terkenali lebih sedikit tidak menimpa item tersimpan.

**Lokasi**: [api_adapter.py:169-197](../../companion/equipment/api_adapter.py).

Bukti dari `runtime/loadouts/BOMSHAK.json`:

```
Item Class: Construct Crossbow      <- seharusnya "Crossbows"
Rarity: Rare
Skull Core
Construct Crossbow
--------
--------                            <- blok properties kosong
96% increased Physical Damage
...
```

- **Properties hilang**: nama properti di API PoE2 memakai markup (mis. `[Evasion] Rating`). Hanya mod yang dibersihkan oleh `_clean_mod` di MCP, nama properti tidak. Akibatnya kecocokan `"Evasion Rating"`/`"Armour"`/`"Physical Damage"` gagal. Helmet "Plague Crest" tidak punya Evasion/ES base, dan crossbow tidak punya damage/APS/crit.
- **Requirements, item level, implicit base** tidak ditulis, sehingga cek atribut (headroom Str/Dex/Int) untuk item saat ini buta.
- **Mod yang dibuang**: `desecratedMods` dan `mutatedMods` (yang dinormalisasi oleh MCP) tidak dimasukkan.
- **`Item Class` diisi base type**; item magic memakai nama penuh sebagai base type (`Smouldering Iron Ring of the Starfish`).

Dampaknya: tanpa PoB2 (Docker mati / token expired), heuristic membandingkan kandidat (teks clipboard lengkap dengan armour/evasion base) dengan item current (local defense 0). Kandidat jadi terlihat lebih unggul. Tactical advice di jalur PoB2 juga memakai `current_raw` ini jika `get_equipped` PoB2 tidak memberi `raw`.

**Perbaikan**: bersihkan nama properti dengan regex yang sama dengan `_clean_mod`, tulis semua properti (`name: value`, termasuk elemental damage, APS, crit, reload), requirements, dan `itemLevel`, sertakan desecrated/mutated mods, dan gunakan `baseType` untuk base serta kelas item yang benar. Lebih baik lagi: ambil `raw` per slot dari `get_equipped` PoB2 setelah import (teks item PoB2 sudah lengkap) dan simpan itu sebagai `raw_text` loadout.

## 5. Compare manual vs auto-scan memakai jalur berbeda (Tinggi)

**Lokasi**: [compare.js:501](../../dashboard/js/compare.js), [compare.js:589](../../dashboard/js/compare.js), [dashboard_api.py](../../companion/dashboard_api.py) `_pob2_fubgun_weapon`.

- **Compare manual** (tombol "Bandingkan" / paste) selalu mengirim `slot: targetSlot` hasil deteksi di browser. Di server, `requested_slot` yang terisi berarti:
  - target slot router diabaikan (`if not req: pob_slot = route_res.target_slot`),
  - `simulate_weapon_plan` (toggle weapon set, skill context, clear slot 2H) tidak pernah dipakai,
  - cabang 1H ambigu tidak pernah dipakai,
  - `skill_context=None` di policy senjata.
  Untuk build Fubgun (Set 1 / Set 2), compare manual pada senjata hanya memakai `simulate_item` biasa.
- **Auto-scan** (`/api/clipboard-poll`) tidak mengirim slot, jadi server menjalankan router penuh. Tapi UI lalu menimpa `data.slot = targetSlot` dengan deteksi browser dan mengabaikan `recommended_slot`. Hasilnya, verdict yang server hitung untuk Ring 2 / Weapon 1 Swap disimpan di riwayat slot lain, dan tombol "Pasang" memasang ke slot tersebut.

Akibatnya item yang sama bisa mendapat verdict berbeda tergantung cara item itu masuk.

**Perbaikan**: compare manual mengirim `slot` hanya jika user memilih slot secara eksplisit (misalnya kotak "kunci slot"). Di UI, hormati `data.slot`/`data.recommended_slot` dari server dan pakai deteksi browser hanya sebagai fallback.

## 6. Cabang senjata 1H ambigu selalu crash (Tinggi)

**Lokasi**: [dashboard_api.py:487](../../companion/dashboard_api.py).

`DualWeaponRecommendation` punya field `slot1_recommendation`/`slot2_recommendation`, bukan `rec1`/`rec2`:

```
fields: ['slot1_recommendation', 'slot2_recommendation', 'recommended_slot', 'summary_verdict', 'trade_off_notes', 'formatted_output']
```

`advice.rec1.gains` memicu `AttributeError`, ditangkap oleh handler PoB2, lalu jatuh ke heuristic (sekarang tercatat di log). Selain itu `verdict=advice.summary_verdict` mengirim kalimat ("Recommended placement: …") sebagai verdict, sehingga UI tidak bisa memberi warna atau badge. `evaluate_dual_weapon_policy` juga tidak diberi `empty_slot1/2`.

**Perbaikan**: pakai `slot1_recommendation`/`slot2_recommendation`, petakan verdict dari rekomendasi slot terpilih (pola yang sama dengan `_pob2_ring`), oper `is_slot_empty`, lalu tambah test.

## 7. Slot Weapon Set 2 eksplisit disimulasikan tanpa mengaktifkan Set 2 (Tinggi, perlu verifikasi live)

**Lokasi**: `_pob2_weapon` (pemetaan `set2_main_hand` ke `"Weapon 1 Swap"`) lalu `simulate_item`.

`simulate_item` memuat XML baseline apa adanya (`useSecondWeaponSet` biasanya `false`) dan memasang kandidat ke slot swap. PoB hanya menghitung weapon set yang aktif, jadi DPS/defense delta kemungkinan ~0, dan policy menghasilkan REJECT ("no DPS upgrade"). Hanya `simulate_weapon_plan` dan `simulate_ambiguous_1h_weapon` yang memanggil `_set_weapon_set_in_xml`. Karena temuan 5, compare manual selalu jatuh ke jalur ini untuk Set 2.

**Perbaikan**: `simulate_item` mengaktifkan set 2 bila slot berakhiran `Swap`, atau jalur senjata dengan slot eksplisit tetap memakai `simulate_weapon_plan` dengan context slot tersebut. Verifikasi dengan satu compare live crossbow Set 2.

## 8. Main skill tidak dikunci untuk ring dan 1H; baseline ring tidak konsisten (Sedang)

**Lokasi**: [pob2_equipment_advisor.py:865](../../companion/equipment/pob2_equipment_advisor.py), [pob2_equipment_advisor.py:1093](../../companion/equipment/pob2_equipment_advisor.py).

- `simulate_item` memanggil `set_main_skill(primary_group)` sebelum dan sesudah equip. `simulate_ring_candidate` dan `simulate_ambiguous_1h_weapon` tidak. Ring dengan `Adds X damage to Attacks` dihitung terhadap main skill default build, dan README sendiri menyebut ini bisa memberi `dps_delta = 0` atau angka keliru.
- `simulate_ring_candidate` memanggil `_build_delta` tanpa `def_before`/`stats_before`, sehingga "before" diambil dari `self.stats_before` (engine utama saat init / `equip_item`), sedangkan "after" dari sandbox. Setelah `_recover_session`, `self.stats_before` dihitung dengan main skill terkunci, sementara "after" ring tidak. Delta DPS ring jadi campuran dua konteks skill.

**Perbaikan**: samakan dengan `simulate_item`: ukur before/after di sandbox yang sama dengan main skill terkunci.

## 9. Baseline PoB2 basi dan stage salah (Sedang)

> **Diperbaiki** pada `fba254f, 29b1995`: refresh sesi saat level/zone berubah atau umur >10 menit, jeda minimal 60 dtk; level terbaru dipakai. Hanya diverifikasi dengan unit test, belum live.

- Sesi PoB2 diimpor sekali (saat start / pilih karakter) dan hanya di-refresh lewat invalidate (temuan 3) atau "Pasang" dari dashboard. Ganti gear atau naik level di game tidak memicu refresh. Compare dilakukan terhadap gear lama.
- [dashboard_api.py:284](../../companion/dashboard_api.py): `char_level` diambil dari `pob_session.level` (saat import) dan **mengalahkan** level di `runtime/characters/*.json`, yang lebih segar (ditulis oleh observer / update stats). Stage `auto` bisa tertinggal. Misalnya level 37 menjadi 53 tetap dianggap `LEVELING_33_51` (pre-swap), sehingga aturan build-breaker post-swap mati.

**Perbaikan**: ambil level tertinggi dari kedua sumber (atau prioritaskan file karakter), dan tambahkan refresh sesi berbasis TTL atau saat level/zone berubah, menggunakan `sync_character()` di thread background.

## 10. Threshold absolut dan label "%" yang salah (Sedang)

- `dps_delta` adalah selisih absolut `CombinedDPS`. [dashboard_api.py:402](../../companion/dashboard_api.py) dan [dashboard_api.py:410](../../companion/dashboard_api.py) menampilkannya sebagai `"+150.0% DPS"`.
- Policy memakai ambang absolut kecil: `dps_delta <= -2.0` (veto slot ofensif), `ehp_delta < -1.0` (net downgrade), `> 5.0` (gain sekunder), `>= 5.0` (upgrade senjata decisive). Di level 80 dengan DPS puluhan ribu dan EHP ribuan, angka ini setara noise. Di level 5 angka yang sama besar. `PobEquipmentDelta` sudah membawa `dps_before`/`ehp_before`, jadi persentase bisa dihitung.

**Perbaikan**: tampilkan persen dari `dps_before` (dengan guard nol) dan ubah ambang menjadi relatif (mis. ±1% DPS, ±0.5% EHP), dengan batas absolut minimum untuk level rendah.

## 11. Auto-pasang ke slot kosong mengabaikan verdict (Sedang)

**Lokasi**: [compare.js:605](../../dashboard/js/compare.js).

Saat toggle "Auto-Pasang Slot Kosong" aktif dan slot di loadout lokal kosong, item **apa pun** yang di-copy langsung dipasang. Ini termasuk item REJECT, build-breaker, senjata yang tidak kompatibel untuk Sorceress, atau item yang cuma ingin dilihat dari stash/vendor. `/api/equip-item` juga menyuntikkan item itu ke baseline PoB2 (`equip_item`), sehingga semua compare berikutnya membandingkan terhadap item yang tidak benar-benar dipakai. Status "kosong" diambil dari loadout file, bukan dari PoB2.

**Perbaikan**: pasang otomatis hanya bila `verdict === 'EQUIP_NOW'` dan slot kosong menurut server (`engine_status`/PoB2), atau default toggle mati.

## 12. Import GGG: baseline kosong, nilai tidak diperbarui, ghost item (Sedang)

> **Sebagian diperbaiki** pada `17246e2, bf0dbb7, 0b4cbe9`: import resmi mulai dari draft kosong; hanya fakta MANUAL yang dilindungi; baseline dari PoB2 disimpan. Fakta manual yang dipertahankan ditandai STALE bila gear berubah (fix wave final review), dan slot yang dilaporkan PoB2 kosong ikut dikosongkan. Default kelas 'Mercenary' tidak diubah. Belum diverifikasi live.

**Lokasi**: [api_adapter.py:245](../../companion/equipment/api_adapter.py), [dashboard_api.py](../../companion/dashboard_api.py) `import_character_payload`.

- Adapter selalu mengembalikan `CharacterStatBaseline.create_empty(...)`. Import resmi tidak pernah mengisi life/res/atribut, padahal PoB2 sudah menghitungnya (`get_defenses` / `calc_stats` di sesi).
- `import_character_payload` lalu menyalin **semua** fakta lama yang `is_known` ke baseline baru. Karena baseline baru kosong, efektif baseline tidak pernah berubah oleh import. Nilai OFFICIAL lama juga tidak pernah ditimpa, padahal yang sepatutnya dilindungi hanya `MANUAL_USER_INPUT`.
- Loadout baru dimulai dari salinan loadout lama, lalu slot dari API ditimpa. Slot yang sekarang **kosong** di game (item dilepas) tidak ada di payload, jadi item lama tetap tercatat.
- Kelas default `"Mercenary"` jika payload tidak membawa kelas.

**Perbaikan**: isi baseline dari PoB2 (life, res efektif, armour/evasion/ES, atribut) saat sesi tersedia. Lindungi hanya fakta bersumber manual. Untuk import resmi (`overwrite=True`), mulai dari loadout kosong untuk slot gear.

## 13. Daftar karakter akun tidak pernah dari GGG (Sedang)

> **Diperbaiki** pada `cbe3e49, 1b4c677`: daftar karakter dari GGG API; fallback palsu dihapus. Hanya diverifikasi dengan unit test, belum live.

**Lokasi**: [dashboard_api.py:1386](../../companion/dashboard_api.py), [dashboard_api.py:1442](../../companion/dashboard_api.py).

`get_account_characters` membaca `path-of-building-2-mcp/oauth_status.json`. File itu adalah status alur login OAuth (`{"status": "WAITING_FOR_USER", "authorize_url": ...}`, terakhir diubah 4 Okt) dan tidak punya key `characters`. Daftar karakter selalu hanya berasal dari file lokal. Jika kosong, isinya fallback palsu `BOMSHAK lvl 19 "Forbidden Rites"`. MCP sudah menyediakan `poe_api.list_characters()` (`GET /character/poe2`).

**Perbaikan**: panggil `poe_api.list_characters()` saat token valid (cache beberapa menit), gabungkan dengan file lokal, dan hapus fallback palsu.

## 14. Error OAuth ditelan; pesan error menyesatkan (Sedang)

> **Diperbaiki** pada `cbe3e49`: error OAuth/API ditampilkan apa adanya, tanpa fallback ke endpoint lama. Hanya diverifikasi dengan unit test, belum live.

**Lokasi**: `fetch_public_profile`, blok `except Exception: pass` setelah jalur `poe_oauth`/`poe_api`.

Semua kegagalan jalur resmi (token expired, 401, 429 rate limit, 404 nama karakter salah) dibuang. Kode lalu mencoba `character-window/get-items`, yang menurut pesan error kode itu sendiri tidak melayani PoE2. User mendapat pesan "akun PRIVATE / 403" atau "404 endpoint warisan", padahal penyebab sebenarnya misalnya `rate limited (429)` atau `session invalid, log in again`.

**Perbaikan**: jika backend MCP ada, kembalikan pesan `PoEApiError`/`OAuthError` apa adanya, dan jangan jatuh ke endpoint lama (endpoint itu sekaligus menyamar sebagai User-Agent Chrome).

## 15. Aturan Fubgun diterapkan ke guide lain (Sedang)

Engine heuristic dan `_build_eval_context` selalu menjalankan `FubgunOilGrenadeFireRule`, apa pun `guide`-nya. Stage Navira dipetakan ke enum Fubgun (`"early endgame"` menjadi `LEVELING_53_68`, post-swap). Akibatnya item Sorceress dengan fire damage to attacks bisa ditolak dengan alasan "Oil Grenade". Sebaliknya, setelah temuan 1 diperbaiki, gate harus aktif hanya untuk guide `fubgun_flameblast`.

**Perbaikan**: oper `guide` ke safety gate dan aktifkan aturan Fubgun hanya untuk guide Fubgun.

## 16. Counter staleness dipakai bersama (Rendah)

`submit_candidate` menaikkan satu counter per sesi. Klik evaluate manual dan auto-scan clipboard (thread server berbeda) memakai sesi yang sama. Jika keduanya berjalan bersamaan, simulasi pertama dianggap stale dan mengembalikan `None`, lalu jatuh ke heuristic (sekarang tercatat sebagai "PoB2 returned no delta"). Desain latest-wins ini cocok untuk satu sumber input, tapi tidak untuk dua.

**Perbaikan**: staleness per sumber (manual vs auto), atau jalur manual tidak ikut coalescing.

## 17. Heuristic tanpa model offense (Rendah)

`_evaluate_heuristic` dan `EquipmentIntelligenceEngine` hanya menghitung life/res/armour/evasion/ES/MS/atribut. `companion/equipment/weapon_projection.py` tidak di-import di mana pun (dead code). Tanpa PoB2, verdict senjata murni berbasis defense, dan badge "⚠ Estimasi heuristik" sekarang menandai kondisi ini.

**Perbaikan**: di mode heuristic untuk senjata, tampilkan verdict `INSUFFICIENT_DATA` (bukan EQUIP/REJECT), atau sambungkan `weapon_projection`.

## 18. Deteksi slot UI (Rendah)

[compare.js](../../dashboard/js/compare.js) `detectSlotFromItemText`: `itemClass.includes('staff')` tidak cocok dengan `"Staves"`/`"Quarterstaves"`. Untuk item normal/magic, `baseType` kosong (baris ke-2 setelah Rarity adalah `--------`), sehingga hasil jatuh ke slot yang sedang dipilih. Senjata hanya masuk Set 2 jika user sudah memilih slot Set 2.

**Perbaikan**: cocokkan `Item Class` resmi PoE2 dengan tabel eksplisit. Lebih baik lagi, biarkan server yang menentukan slot (lihat temuan 5).

---

## Urutan perbaikan yang disarankan

1. Temuan 1, 2, 15: satu safety gate di awal `_evaluate_item_payload_impl` yang sadar guide, plus `merge_verdicts` di jalur heuristic. Tambah test probe gloves di atas.
2. Temuan 3: tutup engine di invalidate dan init gagal (perubahan kecil, menghentikan kebocoran container).
3. Temuan 6 dan 10 (label): bug lokal kecil.
4. Temuan 5, 7, 11: satukan jalur manual dan auto (server yang menentukan slot), Set 2 diaktifkan di simulasi, auto-pasang hanya untuk EQUIP_NOW.
5. Temuan 4, 12, 13, 14: perbaiki adapter import (properties, requirements, baseline dari PoB2, ghost slot), daftar karakter dari `list_characters`, dan error OAuth yang jujur.
6. Temuan 8, 9, 10 (threshold), 16, 17, 18: akurasi dan ketahanan.

---

## Verifikasi live (Phase 0, 2026-10-11)

Dashboard + Docker + token MCP valid. Karakter BOMSHAK, 3x `POST /api/fetch-public-profile`: jumlah container PoB2 tetap 4 sebelum dan sesudah tiap sync (tidak bertambah). Angka 4 berarti dua sesi (satu `docker run` per engine, dua engine per sesi): sisa dari race pembuatan sesi serentak, yang baru ditutup di fix wave. Setelah server dihentikan, container turun ke 0.

Catatan koreksi: `runtime/loadouts/BOMSHAK.json` helmet `raw_text` yang diperiksa (`Item Level: 40`, `Evasion Rating: 37`, `Energy Shield: 18`) adalah teks hasil adapter GGG, bukan teks PoB2. Pengecekan ini memverifikasi temuan 4 sisi GGG saja.
