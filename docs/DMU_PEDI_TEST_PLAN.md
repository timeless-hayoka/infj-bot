# DMU & PEDI Testing Methodology

This document outlines the formal testing strategy for the Dynamic Memory Unit (DMU) and the Performance and Efficiency Detection Index (PEDI).

---

## 1. DMU (Dynamic Memory Unit) Testing
The DMU regulates memory salience using the formula:
$W_{final} = (BaseScore) \cdot e^{-\lambda (\Delta t)} \cdot (1 + \alpha \cdot Resonance)$

### 🧪 Test Cases (`tests/test_dmu.py`)
- **Exponential Decay Verification:** Use `pytest` to verify that memory scores decrease over simulated time intervals when resonance is constant.
- **Resonance Multiplier Test:** Confirm that high emotional resonance values (from the `Aura` layer) can override temporal decay, keeping critical memories "fresh."
- **Collection Boundary Test:** Ensure retrieved collections from ChromaDB are correctly re-ranked without loss of metadata.
- **Null Safety:** Verify the engine handles memories with missing timestamps or resonance scores gracefully.

---

## 2. PEDI (Performance & Efficiency Detection Index) Testing
PEDI calculates the organism's efficiency ratio based on hardware load and API performance.

### 🧪 Test Cases (`tests/test_pedi.py`)
- **Metric Collection:** Mock the `google.generativeai` response metadata to verify `tokens_per_second` is captured accurately.
- **Latency Sensitivity:** Simulate high-latency network conditions and verify that the PEDI score reflects a decrease in efficiency.
- **Resource Correlation:** Verify the somatic link between `host_load.py` (CPU/RAM) and the PEDI efficiency curve.
- **Data Persistence:** Ensure PEDI results are correctly serialized to the `pedi_logs.db` SQLite database for longitudinal research.

---

## 3. Integrated Research Validation
A combined test suite will be run periodically to analyze the correlation between **Memory Freshness (DMU)** and **Cognitive Efficiency (PEDI)**. Results will be logged to `~/.drift_os/logs/research_audit.jsonl`.
