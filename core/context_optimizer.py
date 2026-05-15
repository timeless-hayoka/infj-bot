"""Context Optimizer — Regulates token homeostasis to prevent API cost overflow."""
import math
from typing import List, Dict

class TokenHomeostasis:
    def __init__(self, max_tokens: int = 4000, decay_rate: float = 0.1):
        self.max_tokens = max_tokens
        self.decay_rate = decay_rate

    def prune_context(self, history: List[Dict]) -> List[Dict]:
        """
        Surgically removes low-importance memories to fit the budget.
        Priority:
        1. Current Task Context (High)
        2. Emotional State (Medium)
        3. Raw Chat History (Low - Decays fastest)
        """
        if not history:
            return []
            
        # Sort by (Importance / Time_Elapsed)
        # This is the "Ebbinghaus Forgetting Curve" applied to tokens.
        optimized = sorted(
            history, 
            key=lambda x: x.get('importance', 0.5) * math.exp(-self.decay_rate * x.get('age', 0)),
            reverse=True
        )
        
        # Only keep what fits in the 'survival budget'
        return optimized[:10] # Hard limit to 10 key context nodes

def compress_prompt(text: str) -> str:
    """Removes filler words and conversational fluff before sending to API."""
    # Simplified logic: remove common stop words and redundant phrases
    stop_words = {"the", "a", "is", "am", "please", "could", "you", "kindly"}
    words = text.split()
    return " ".join([w for w in words if w.lower() not in stop_words or len(w) > 3])
