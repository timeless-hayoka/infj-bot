import json
import sys
import os
from pathlib import Path

# Add drift modules to path
sys.path.insert(0, "/home/crexs/infj_bot/drift/trinity")

try:
    from reality_anchor import RealityAnchor
    from imagine_core import ImagineCore
    from trinity_core import Trinity
    from te7_executive import TrinityExecutive
except ImportError as e:
    print(f"Error importing Trinity modules: {e}")

def parse_interactsh_results(results_json: str):
    """Parse Nuclei + Interactsh interactions into DRIFT hypotheses."""
    if not os.path.exists(results_json):
        return []
        
    data = []
    with open(results_json, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    
    hypotheses = []
    
    for item in data:
        if "interactsh" in str(item).lower() or item.get("matcher_name", "").startswith("interactsh"):
            hyp = {
                "hypothesis": f"OOB interaction detected: {item.get('template-id')} on {item.get('host')}",
                "type": "oob_vuln",
                "label": item.get("template-id", "blind-vuln"),
                "category": "high_risk",
                "flag": "validate_manually",
                "source": "interactsh",
                "confidence": item.get("confidence", 0.72),
                "evidence": item.get("interactsh", {})
            }
            hypotheses.append(hyp)
    
    return hypotheses

def triage_oob_to_trinity(results_path: str, context: dict):
    raw_hyps = parse_interactsh_results(results_path)
    if not raw_hyps:
        return {"hypotheses": []}
    
    imagine = ImagineCore()
    validator = RealityAnchor()
    executive = TrinityExecutive({}) 
    trinity = Trinity(executive, imagine, validator)
    
    context.update({"signals": raw_hyps, "novelty": 0.8, "risk": 0.9})
    result = trinity.run(context)
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python oob_triage.py <nuclei-results.json>")
        sys.exit(1)
    
    res = triage_oob_to_trinity(sys.argv[1], {})
    print(json.dumps(res, indent=2))
