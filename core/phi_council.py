"""
PHI Council of Seven - The Internal Governance of the Drift Model.
Company: PHI
Model: Drift
"""

COUNCIL_MAPPING = {
    "Aura": "emotional_field",
    "Logic": "cognition",
    "Meme": "metacognition",
    "Vibe": "intuition",
    "Ethos": "values",
    "Pulse": "homeostasis",
    "Nexus": "coordination",
}


def get_council_name(module_name: str) -> str:
    for name, module in COUNCIL_MAPPING.items():
        if module == module_name:
            return name
    return module_name
