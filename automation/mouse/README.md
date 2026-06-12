# 🖱️ MOUSE (Mobile Operations Utility & Synthetic Evaluator)

**The On-The-Go Bug Bot.** 

MOUSE is an advanced, lightweight automation framework designed for the INFJ-Bot and the broader PHI//DRIFT ecosystem. Its primary function is to serve as an autonomous, roaming testing and evaluation agent. If the Forge Protocol is the heavy-duty stress testing facility, MOUSE is the nimble scout you deploy into the field to hunt down bugs, validate UI workflows, and stress-test code changes on the fly.

---

## 🌟 Why MOUSE?
Most testing frameworks require rigid, brittle scripts. MOUSE uses visual understanding, cognitive reasoning (via Ollama/Qwen), and synthetic persona emulation to navigate interfaces and systems *like a real human user*.

*   **On-The-Go Execution:** Run it directly from the terminal without heavy IDE setups.
*   **Cognitive Bug Hunting:** MOUSE doesn't just click buttons; it evaluates the *state* of the application, detects anomalies, and logs causal failures.
*   **Vanguard Integration:** Fully integrated with the `mouse_vanguard` protocol to ensure deep security and state-tracking.

## 🛠️ Key Features
*   **V1 & V2 Capabilities:** Incremental levels of autonomy, from scripted operations to full vision-language model driven exploration.
*   **Vision-Enabled:** Can parse UI elements and determine if a button is clickable or if a layout is broken.
*   **Self-Healing:** If an element is missing, MOUSE recalibrates and attempts an alternative path.

## 🚀 Quick Start
To dispatch MOUSE into a directory or against a live URL:
```bash
python3 v2.py --target "https://localhost:8000" --mode hunt
```

## 🛒 Licensing
MOUSE is part of the PHI//DRIFT ecosystem. The full open-source version is available here. 
For production-grade enterprise testing, an advanced version of MOUSE is included in the **Forge Testing Framework PRO** or can be acquired independently from the A.F.P Store.
