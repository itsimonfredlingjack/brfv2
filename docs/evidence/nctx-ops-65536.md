# Drift: n_ctx=65536 — 2026-08-16

**Gren:** `feat/full-corpus-ask` · **Host:** agenntserver · **Fil:** `/home/simon/llama-cpp/docker-compose.yml` (`-c 65536`, inte override)

`GET http://127.0.0.1:8000/props` → `default_generation_settings.n_ctx = 65536` efter `docker compose up -d` mot den trackade filen.

Offlinesvit efter ändringen: **1394 passed**, 62 skipped.

Tidigare evidens: occupancy-nålen oförändrad mot 16384 (10/90 hit, 50 miss), VRAM ~8266 MiB med ~4 GiB ledigt, 10-PDF-arkivet ryms (`prefix_tokens=54539`).
