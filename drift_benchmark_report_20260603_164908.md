# DRIFT Benchmark Report
**Generated:** 2026-06-03 16:49:08  
**Target:** http://localhost:8765  
**DB Directory:** /home/crexs/.drift_os  

---

## System Status
- Status: **ONLINE**
- Health check latency: 7.3ms

## Math Reasoning (GSM8K)
- *Skipped — no live endpoint*

## Behavioral Consistency
- *Skipped — no live endpoint*

## Memory Persistence
- *Skipped — no live endpoint*

## PEDI State Continuity
- Snapshots logged: **1,162**
- Reports logged: **546**
- Dimension drift (first → latest session):
  - energy: ▼0.196
  - coherence: ▲0.220
  - integration: ▲0.363
  - connection: ▼0.070
  - growth: ▲0.195
  - autonomy: ▲0.306
  - integrity: ▲0.463
- **Total absolute drift: 1.812** (across 7 dimensions)
- ⚠ pedi_reports fluidity_score bug detected — use snapshot drift data

## DII Aliveness Index
- **Samples logged: 154,719**
- DII range: 0.0003 – 0.2058  (avg 0.0068)

## Homeostatic Stability
- Need-history rows: **6,156**
- Crisis events: **98**
- Max value swings per need:
  - energy: 0.738
  - integration: 0.731
  - coherence: 0.54
  - growth: 0.289
  - autonomy: 0.206
  - connection: 0.13
  - integrity: 0.08

## Notes
- Production environment: DigitalOcean droplet since June 1.
- PEDI per-turn fluidity_score is hardcoded to 1.0 — use snapshot drift for continuity metrics.
- DII integration/embodiment components average near zero — verify if decay is intended.
- Benchmark is reproducible: rerun anytime against live system.

---
*DRIFT Benchmark Suite v1.1*