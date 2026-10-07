# PoE2 Companion

Personal local AI journey director and advisor for Path of Exile 2.

## Integrasi PoB2 MCP (Model Context Protocol)

Sistem ini menggunakan **Path of Building 2 (PoB2)** sebagai *headless simulation engine* untuk menghitung DPS, EHP, dan stat delta secara akurat. Integrasi dilakukan melalui IPC (Inter-Process Communication) ke server MCP PoB2.

### 1. Resolusi Path MCP Server
Companion akan mencari direktori `path-of-building-2-mcp` dengan urutan prioritas berikut:
1. Parameter eksplisit di kode.
2. Environment variable `POB2_MCP_PATH`.
3. Direktori sibling (`../path-of-building-2-mcp`).
4. Path default Windows (`C:/Projects/path-of-building-2-mcp`).

Jika modul `pob_mcp` berhasil diimpor dari path tersebut, Companion akan menggunakan engine PoB2 asli. Jika gagal, sistem akan jatuh ke mode *fallback heuristic* (estimasi stat tanpa engine).

### 2. Cara Kerja Engine Bridge
- **Headless LuaJIT**: Companion menjalankan PoB2 secara headless via `mcp_entry.lua` dan berkomunikasi menggunakan protokol JSON over `stdio`.
- **Stateful Mutation & Recovery**: Setiap simulasi memanggil `engine.call("equip_item", ...)`. Sistem mengunci *active skill* (misal: `CROSSBOW_LEVELING`) dan me-restore baseline XML sebelum dan sesudah simulasi untuk mencegah polusi state.
- **Dual-Slot Handling**: Mendukung evaluasi kompleks seperti *Dual-Ring* (Pareto evaluation) dan *Weapon Set 1 vs Set 2* (Swap isolation).
- **Live GGG OAuth**: Menggunakan token OAuth dari `%LOCALAPPDATA%/pob2-mcp/token.json` untuk menarik data karakter live dari API resmi GGG.

### 3. Menjalankan Dashboard
Jalankan dashboard web lokal (auto-scan clipboard untuk evaluasi item):
```bash
uv run python -m companion.cli dashboard
```
