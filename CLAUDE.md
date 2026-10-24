# CLAUDE.md: PoE2 Companion

Penasihat dan pengarah perjalanan AI lokal untuk Path of Exile 2. Python 3.11+, uv, pydantic. Detail integrasi PoB2 ada di `README.md`; arsitektur di `docs/architecture/`.

## Perintah

- `uv sync --extra dev`: pasang dependensi + alat tes
- `uv run pytest -q`: semua tes (sekitar 1350 tes, sekitar 55 detik); satu berkas: `uv run pytest tests/<path> -q`
- `uv run python -m companion.cli --help`: CLI (`sources`, `state`, `objectives`, `evaluate`, `session`, `gear`, `api`, `runtime`, `observe`, `dashboard`, ...)
- `uv run python -m companion.cli dashboard --port 8799 --no-browser`: dashboard lokal (konfigurasi `dashboard` di `.claude/launch.json`)

## Struktur

- `companion/`: paket utama; satu subpaket per domain (`api` = GGG API + PoB2, `sensing` = Client.txt/proses, `vision`, `gear`, `objectives`, `rules`, `state`, `runtime`, `observe`). Entri CLI `companion/cli.py`, server dashboard `companion/dashboard_server.py` + `dashboard_api.py`.
- `dashboard/`: frontend statis (`index.html`, `js/`, `style.css`, `bookmarklet.js`), tanpa build step.
- `tests/`: mengikuti struktur `companion/`.
- `openspec/`: alur spec-driven. Spesifikasi kapabilitas di `openspec/specs/<kapabilitas>/`, perubahan aktif di `openspec/changes/`. Skill `openspec-*` ada di `.hermes/skills/`. Perubahan perilaku: perbarui spec yang terkait.
- `runtime/`: state lokal (loadout, baseline, cadangan). Diabaikan git; jangan di-commit.

## Aturan

- Repo ini PUBLIK. Setiap commit adalah publikasi.
- Jangan membaca, menyalin, atau mencetak token OAuth GGG di `%LOCALAPPDATA%/pob2-mcp/token.json` maupun isi `.env`.
- Hanya kerja repo ini yang masuk ke sini; kode dari checkout lain (financial-saas-pr59, Understand-Anything, senior-office) tidak di-port tanpa izin pengguna.
- Engine PoB2 butuh Docker dan repo sibling `path-of-building-2-mcp`; tanpa keduanya compare jatuh ke heuristik. Jangan anggap hasil heuristik sebagai hasil engine.
- Commit: conventional commits, bahasa Inggris. Jangan push tanpa diminta.
