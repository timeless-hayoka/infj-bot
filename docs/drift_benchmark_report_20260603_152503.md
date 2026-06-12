# DRIFT Benchmark Report
**Generated:** 2026-06-03 15:25:03  
**Target:** http://localhost:8765  
**DB Directory:** .  

---

## System Status
- Status: **ONLINE**
- Health check latency: 11.9ms

## Math Reasoning (GSM8K)
- **Accuracy: 19/20 (95.0%)**
- Latency p50: 7092.5ms  |  p95: 14501.7ms
- Environment: DigitalOcean droplet (since June 1)

## Behavioral Consistency
- **Average cross-run similarity: 79.6%**
  - Prompt 1: 83.9%
  - Prompt 2: 76.5%
  - Prompt 3: 78.3%

## Memory Persistence
- **Recall accuracy: 3/3 (100%)**

## PEDI State Continuity
- Snapshots logged: **0**

## DII Aliveness Index
- **Samples logged: 0**

## Notes
- Production environment: DigitalOcean droplet since June 1.
- PEDI/DII databases empty — these metrics exist in code but have no production runtime data yet.
- Homeostasis database has zero recorded need_history rows — stability claims are unmeasured.
- Benchmark is reproducible: rerun anytime against live system.

---
*DRIFT Benchmark Suite v1.0*