# DRIFT Benchmark Report
**Generated:** 2026-06-03 16:45:03  
**Target:** http://localhost:8765  
**DB Directory:** /home/crexs/.drift_os  

---

## System Status
- Status: **ONLINE**
- Health check latency: 10.3ms

## Math Reasoning (GSM8K)
- **Accuracy: 19/20 (95.0%)**
- Latency p50: 7936.0ms  |  p95: 10376.9ms
- Environment: DigitalOcean droplet (since June 1)

## Behavioral Consistency
- **Average cross-run similarity: 75.6%**
  - Prompt 1: 77.8%
  - Prompt 2: 75.3%
  - Prompt 3: 73.8%

## Memory Persistence
- **Recall accuracy: 3/3 (100%)**

## PEDI State Continuity
- Snapshots logged: **1,162**
- Dimension drift (first → latest session):
  - energy: ▼0.196
  - coherence: ▲0.220
  - integration: ▲0.363
  - connection: ▼0.070
  - growth: ▲0.195
  - autonomy: ▲0.306
  - integrity: ▲0.463
- **Total absolute drift: 1.812** (across 7 dimensions)
- ⚠ pedi_reports fluidity_score bug detected — use snapshot data

## DII Aliveness Index
- **Samples logged: 154,658**
- DII range: 0.0003 – 0.2058  (avg 0.0068)

## Notes
- Production environment: DigitalOcean droplet since June 1.
- PEDI/DII databases empty — these metrics exist in code but have no production runtime data yet.
- Homeostasis database has zero recorded need_history rows — stability claims are unmeasured.
- Benchmark is reproducible: rerun anytime against live system.

---
*DRIFT Benchmark Suite v1.0*