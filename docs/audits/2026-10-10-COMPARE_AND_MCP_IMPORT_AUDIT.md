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

---

## Cek ulang terhadap kode (2026-10-12, `main` @ 1979149)

Phase 2–4 mengganti jalur compare dengan satu pipeline (`companion/equipment/evaluation.py`) dan menghapus modul Fubgun (`fubgun_rules.py`, `fubgun_weapon_router.py`, `engine.py`). Status tiap temuan dibaca dari kode saat ini:

| # | Status sekarang | Bukti |
|---|---|---|
| 1 | Diperbaiki | `evaluate()` menjalankan `breaker_reasons` (`safety.py`) per slot plan **sebelum** PoB2/heuristic, untuk semua engine dan slot |
| 2 | Diperbaiki | Tactical hanya lewat `merge_verdicts` (veto-only: REJECT dari mana pun menang; tactical tidak pernah mempromosikan) |
| 3 | Diperbaiki | `invalidate_pob_session` menyimpan sesi dan hanya `sync_character()`; sesi basi di `get_or_create_pob_session` di-`close()` |
| 4 | Sebagian | Teks GGG lengkap (properti, requirements, desecrated/mutated). Teks PoB2 → clipboard belum diverifikasi live |
| 5 | Diperbaiki | `compare.js` hanya mengirim `slot` saat "kunci slot" dicentang; UI memakai `data.slot` dari server |
| 6 | Tidak berlaku lagi | Cabang 1H ambigu / `DualWeaponRecommendation` dihapus; `resolve_slots` memberi slot plan |
| 7 | Diperbaiki di kode, belum live | `measure()` mengaktifkan weapon set 2 untuk slot `* Swap` (`_set_weapon_set_in_xml`) |
| 8 | Diperbaiki | `measure()` mengunci main skill sebelum before dan after, di sandbox yang sama, untuk semua slot |
| 9 | Diperbaiki (unit test) | lihat catatan di atas |
| 10 | Diperbaiki | `policy.py` memakai ambang relatif (`DPS_UP=0.01`, `EHP_UP=0.02`, dst.) dan persen dari nilai before |
| 11 | Diperbaiki | `auto_equip_ok = verdict == "EQUIP_NOW" and slot_empty` dihitung server; UI hanya memasang jika true |
| 12 | Sebagian | Default kelas `"Mercenary"` masih ada (`dashboard_api.py:291`, `:348`, `:696`, `state/schema.py:43`); kelas hanya untuk tampilan |
| 13, 14 | Diperbaiki (unit test) | lihat catatan di atas |
| 15 | Diperbaiki | Aturan breaker adalah data per guide (`GuideProfile.breaker_rules`); tanpa guide tidak ada aturan |
| 16 | Diperbaiki | Staleness per `source` (`_latest_by_source`) |
| 17 | Diperbaiki (perilaku) | Tanpa PoB2, slot senjata → `INSUFFICIENT_DATA` ("Tanpa PoB2 senjata tidak bisa dinilai"). `weapon_projection.py` masih dead code (hanya dipakai test) |
| 18 | Diperbaiki | Tabel eksplisit `ITEM_CLASS_TO_SLOT`; fallback talisman diperbaiki di f57b176 |

**Sisa terbuka**
- Verifikasi live untuk 3 (lock pembuatan sesi), 4 (teks PoB2), 7 (Set 2), 9, 12, 13, 14: butuh Docker dan login OAuth MCP (status saat cek: `WAITING_FOR_USER`).
- 12: default kelas `"Mercenary"` saat payload tanpa kelas.
- 17: `weapon_projection.py` (+3 file test) bisa dihapus.

---

## Verifikasi live (2026-10-12, `main` @ 1cf85ae)

Dashboard (`companion.cli dashboard --port 8799`), Docker, token OAuth MCP valid (`oauth_status.json` status `SUCCESS`). Karakter: BOMSHAK (Mercenary3, lvl 56) dan DaisyofWar (Witch3, lvl 71). Runtime dicadangkan sebelum uji; perubahan uji (level, slot hantu, assignment guide) dikembalikan sesudahnya.

| # | Hasil | Bukti |
|---|---|---|
| 3 | Terverifikasi live | BOMSHAK: 4x `fetch-public-profile`, 2 container sebelum dan sesudah tiap sync. Pilih DaisyofWar: naik ke 4 (2 per karakter). Pilih karakter bolak-balik dan pilih ganda: tetap 4. Init sesi Daisy yang gagal karena 429: tidak menambah container. Server dihentikan: 0. |
| 4 | Terverifikasi live, dengan catatan | Setelah sync, `raw_text` 10 slot BOMSHAK berasal dari PoB2: Requirements tanpa `Str/Dex/Int`, staff membawa `Grants Skill: Level 13 Solar Orb (implicit)` yang tidak ada di teks GGG. Semua slot lolos `parse_item_text`. Catatan: (a) teks PoB2 tidak membawa properti senjata (`Physical Damage`, `Attacks per Second`, `Critical Hit Chance`), yang ada di teks GGG; (b) `Level` req staff 16 di PoB2 vs 36 di GGG; (c) slot tetap berlabel `source: GGG_OFFICIAL_API` walau teksnya dari PoB2; (d) nama berdiakritik beda (`Maelström Span` GGG vs `Maelstrom Span` PoB2), jadi tiap sync dianggap ganti item (revisi naik, fakta ditandai STALE). |
| 7 | Mekanisme terverifikasi; compare dashboard tetap 0 (lihat 19) | Compare crossbow lebih kuat ke `set2_main_hand` (kunci slot): `pob_slot: Weapon 1 Swap`, `dps_delta: 0.0`. Uji langsung di engine dengan XML BOMSHAK: group 7 (Oil Grenade) DPS 0 di set 1, 20.6 → 36.5 di set 2 setelah crossbow dipasang. Aktivasi set 2 di `measure()` bekerja. Delta 0 berasal dari main skill yang dikunci (temuan 19). |
| 9 | Terverifikasi live | Level di `runtime/characters/BOMSHAK.json` dinaikkan 56 → 57, lalu `GET /api/status`: sesi di-sync sekali (baseline ditulis ulang 03:15:55); poll berikutnya tidak memicu ulang. Sebelum level berubah, sesi berumur 5 menit tidak di-refresh. |
| 12 | Terverifikasi live (kecuali kelas) | Baseline DaisyofWar terisi dari PoB2 (`DERIVED_CALCULATION`, `evidence_ref: pob2`, life 1152, ES 880, res). Baseline BOMSHAK seluruhnya `MANUAL_USER_INPUT`: tidak ditimpa, ditandai STALE. Belakangan ternyata nilai MANUAL itu (life 723, res 23/-3/-4) berasal dari `test_dashboard_server_http_evaluate_endpoint`, yang menjalankan server terhadap `runtime/` asli dan memanggil `update-stats` setiap kali pytest jalan; diperbaiki di `ad95c09` (fixture autouse), baseline lama dipindah ke `runtime/backups/2026-10-12-test-pollution/`. Slot hantu: crossbow disuntik ke `weapon_set_2.main_hand` Daisy, refresh via level, slot kembali kosong. Kelas: file karakter Daisy berisi `character_class: Witch3`, `ascendancy: Gemling Legionnaire` (default palsu). |
| 13 | Terverifikasi live | `GET /api/account-characters`: `source: api`, 7 karakter akun dari GGG (plus `Cli Hero` dari file lokal tes). |
| 14 | Terverifikasi live | Sync beruntun memberi `{"error": "GGG_API_ERROR", "message": "rate limited (429) — wait a bit and retry"}`; nama karakter salah memberi `not found (404) — wrong character/realm`. UI menampilkan `message` lewat alert. |
| Phase 4 | Terverifikasi live | DaisyofWar sementara di-assign guide Navira, stage `Late Endgame` (= `pob_stage_id` guide). Helmet ES: `verdict EQUIP_NOW`, `guide.target_fit = {dps_pct: 0.0, ehp_pct: -0.093}` (diukur di XML guide). |

## 19. Main skill hasil import GGG selalu group 1 (Tinggi, baru)

Import karakter dari GGG ke PoB2 menetapkan `mainSocketGroup = 1`. Untuk BOMSHAK, group 1 adalah Virtuous Barrier (buff, DPS 0). `measure()` mengunci main skill ke `self.main_group` sebelum before/after, jadi `dps_delta` BOMSHAK selalu 0 untuk semua slot. Akibatnya senjata dan item ofensif tidak pernah melewati ambang DPS. Skill yang relevan ada di XML (Flameblast group 5, Oil Grenade group 7), tetapi tidak dipilih.

**Perbaikan yang mungkin**: pilih main skill dari guide aktif (mis. skill utama per stage), atau dari group dengan DPS tertinggi saat baseline. Opsi kedua bisa memilih skill dari item (Solar Orb dari staff, 282 DPS), jadi skill dari guide lebih tepat bila tersedia.

## Tindak lanjut (2026-10-12)

- 12 (kelas): diperbaiki di `59114b4`. Kode ascendancy GGG (`Witch3`, `Sorceress1`, ...) dipetakan ke kelas + ascendancy (`internalId` dari TreeData PoB2 0_5); tanpa kelas, nilainya `None` dan dashboard menampilkan `Unknown`. Terverifikasi di dashboard: DaisyofWar tampil "Lich" (sebelumnya "Gemling Legionnaire").
- 17: `weapon_projection.py` sudah dihapus di `1cf85ae`.
- Kode mati sebelum pipeline (`recommendation`, `rules`, `precedence`, `contextual_value`, `data_sufficiency`, `fact_dependencies`) dihapus di `152e316`; `Verdict` pindah ke `tactical_advisor`.
- 19: diperbaiki di kode, belum diverifikasi live. Setiap import/sync, sesi memilih socket group dengan DPS tertinggi di baseline (`mainDPS` PoB, yaitu FullDPS atau CombinedDPS; seri tetap ke group PoB sendiri) dan baseline dibaca dengan group itu. `measure()` menerima `main_skill` dari stage guide aktif (`GuideStage.main_skill`, dicocokkan lewat `find_socket_group_for_skill`); kalau tidak cocok, kembali ke group DPS tertinggi. Alias crossbow/leveling tanpa kecocokan sekarang mengembalikan `None`, bukan group 1. Verifikasi live (crossbow BOMSHAK ke `Weapon 1 Swap` harus memberi delta DPS bukan 0) tertunda: Docker daemon tidak jalan saat dicek (2026-10-12).
- 19, verifikasi live 2026-10-12 (`ef2839f`): **Gagal** untuk skenario crossbow swap. Mekanismenya bekerja: sesi memilih group 2 (Solar Orb, 282.4 DPS di set 1), dan stage guide `lvl 53-68` (`main_skill: Flameblast`) dicocokkan ke group 5. `POST /api/evaluate-item` BOMSHAK, crossbow rare ke `set2_main_hand`: `engine: pob2`, `pob_slot: Weapon 1 Swap`, `dps_delta: 0.0`. Ukuran per group langsung di engine (set 2, sebelum → sesudah crossbow): Flameblast (5) 38.5 → 38.5, Solar Orb (2) 80.4 → 80.4, Oil Grenade (7) 20.6 → 2.5 (crossbow uji lebih lemah dari yang terpasang). Crossbow swap hanya memengaruhi Oil Grenade, padahal skill utama guide (Flameblast) dan group DPS tertinggi (Solar Orb) tidak memakai senjata itu. Jadi delta 0 benar untuk skill yang dikunci, tetapi item swap tidak pernah terukur. Butuh aturan tambahan untuk slot senjata (lihat tindak lanjut).
- 19, perbaikan lanjutan: untuk slot senjata, `measure()` mengukur DPS setiap group aktif sebelum dan sesudah item dipasang, lalu mengunci group dengan perubahan terbesar; kalau tidak ada yang berubah, tetap skill guide / DPS tertinggi. **Terverifikasi live** 2026-10-12: `POST /api/evaluate-item` BOMSHAK ke `set2_main_hand`, `engine: pob2`, `pob_slot: Weapon 1 Swap`. Crossbow uji lemah: `dps_delta -18.05` (`dps_pct -87.7%`), sama dengan Oil Grenade (group 7) 20.6 → 2.5 dari ukuran langsung di engine. Crossbow uji lebih kuat: `dps_delta -10.60` (`-51.5%`). Keduanya lebih lemah dari crossbow yang terpasang, jadi delta negatif itu benar. Waktu respons 7-12 dtk.
- Temuan baru dari verifikasi ini: kedua crossbow tetap mendapat verdict `CONDITIONAL_UPGRADE` walau DPS turun 51-88%, karena `decide()` ([policy.py](../../companion/equipment/policy.py)) hanya REJECT bila DPS turun **dan** EHP tidak naik; +1.6% EHP (life +22) dianggap kompensasi. Sebelumnya tidak terlihat karena delta DPS selalu 0.
- Verdict DPS turun besar: `decide()` sekarang REJECT bila DPS turun lebih dari 20% dan EHP naik kurang dari 5% (`DPS_CRASH`, `EHP_COMPENSATE`). **Terverifikasi live** 2026-10-12: kedua crossbow uji BOMSHAK ke `Weapon 1 Swap` mendapat `REJECT` ("DPS turun lebih dari 20% dan kenaikan EHP di bawah 5%."), `dps_pct` -87.7% / -51.5%, `ehp_pct` +1.6%.
- Fork PoB2 dipindah dari `ce8bffab` ke `origin/dev` `bb52d6b3` (2026-10-12). Upstream mengganti constructor `new("Item", raw)` menjadi `new("Item"):Item(raw)`, sehingga `equip_item` di `engine/mcp_entry.lua` crash ("Extra argument passed to new()"); diperbaiki di repo MCP dan entrypoint disuntik ulang ke fork. Test engine MCP: 33 lulus (`test_fetch` gagal karena `mcp` 2.x, tidak terkait fork). **Terverifikasi live** dengan fork baru: gloves BOMSHAK lewat `pob2` (`EQUIP_NOW`, life +58); crossbow ke `Weapon 1 Swap` `REJECT`, `dps_delta -128.3`. Angka berubah dari -18.05 karena import GGG di fork baru memunculkan group 9 "Crossbow Shot" (skill bawaan crossbow swap, 136.1 → 7.8), yang kini paling terdampak. `pob_base_types.json` bertambah satu base (`Runeforged Warden Bow`).
- Temuan 4, catatan (a)-(d): diperbaiki dari akarnya. Sesi PoB2 menyimpan payload GGG yang dipakai untuk import (`ggg_payload`), dan `apply_session_to_runtime` menulis teks item dari `ggg_item_to_text` untuk setiap slot yang ada di payload itu. Teks PoB2 (`pob_item_to_clipboard`) hanya fallback untuk slot yang tidak ada di payload, dan diberi label `DERIVED_CALCULATION`. Pemetaan `inventoryId` dipindah ke `ggg_slot()` di `api_adapter.py` agar import publik dan sync sesi memakai aturan yang sama. **Terverifikasi live** 2026-10-12 (BOMSHAK): (a) crossbow `Skull Core` membawa `Physical Damage: 35-141`, `Critical Hit Chance: 5.00%`, `Attacks per Second: 1.73`, `Reload Time: 0.74`; (b) staff `Cataclysm Call` `required_level` 36 (sebelumnya 16 dari PoB2); (c) 10 slot `GGG_OFFICIAL_API`, karena teksnya memang dari GGG; (d) `apply_session_to_runtime` tiga kali berturut-turut dengan sesi live pada salinan runtime: revisi tetap 1. Transisi pertama dari teks PoB2 lama ke teks GGG menaikkan revisi sekali (2 → 3). Catatan: nama berdiakritik masih bisa berbeda pada jalur fallback PoB2, yang hanya dipakai bila GGG tidak punya slot itu.
- Masih terbuka: tidak ada dari audit ini.
