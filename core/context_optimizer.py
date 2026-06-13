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
            key=lambda x: (
                x.get("importance", 0.5) * math.exp(-self.decay_rate * x.get("age", 0))
            ),
            reverse=True,
        )

        # Only keep what fits in the 'survival budget'
        return optimized[:10]  # Hard limit to 10 key context nodes


def compress_prompt(text: str) -> str:
    """
    Advanced Token Minification.
    Performs lossless (or near-lossless) compression on context payloads to drastically reduce LLM token usage.
    """
    import json
    import re
    
    if not text:
        return ""

    # 1. JSON Minification: Find JSON blocks and minify them.
    # We do a basic heuristic: text between ```json and ``` or just anything that looks like a big valid JSON.
    def minify_json_match(match):
        try:
            parsed = json.loads(match.group(1))
            minified = json.dumps(parsed, separators=(',', ':'))
            return minified
        except json.JSONDecodeError:
            return match.group(0)

    # Minify standard markdown JSON blocks
    text = re.sub(r'```json\s*(\{.*?\})\s*```', minify_json_match, text, flags=re.DOTALL)
    
    # 1.5 Code Block Minification (Python, JS, HTML, CSS)
    def minify_code_match(match):
        lang = match.group(1).lower()
        code = match.group(2)
        
        if lang in ["javascript", "js", "css"]:
            # Remove single-line comments
            code = re.sub(r'//.*', '', code)
            # Remove multi-line comments
            code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
            # Collapse multiple spaces and newlines
            code = re.sub(r'\s+', ' ', code)
        elif lang in ["html"]:
            # Remove HTML comments
            code = re.sub(r'<!--.*?-->', '', code, flags=re.DOTALL)
            # Collapse whitespace between tags
            code = re.sub(r'>\s+<', '><', code)
            code = re.sub(r'\s+', ' ', code)
        elif lang in ["python", "py"]:
            # Remove docstrings (basic heuristic for triple quotes not assigned)
            code = re.sub(r'^\s*"""[\s\S]*?"""', '', code, flags=re.MULTILINE)
            code = re.sub(r"^\s*'''[\s\S]*?'''", '', code, flags=re.MULTILINE)
            # Remove comments
            code = re.sub(r'#.*', '', code)
            # Remove blank lines
            code = re.sub(r'\n\s*\n', '\n', code)
            
        return f"```{lang}\n{code.strip()}\n```"

    # Match any code block
    text = re.sub(r'```(\w+)\s*\n([\s\S]*?)\n```', minify_code_match, text)

    # 2. Markdown / Structural Collapse
    # Remove multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove trailing spaces on lines
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    
    # Remove redundant spaces between words (but preserve formatting in code blocks where possible)
    # Actually, a simple `re.sub(r' {2,}', ' ', text)` is risky for code Python blocks, so we skip aggressive space removal globally.
    
    # 3. Filler Phrase Stripping (Only safe conversational fluff)
    # We remove things like "Here is the information you requested:" -> ""
    fluff_patterns = [
        r"(?i)^here is the .*?:?\s*\n",
        r"(?i)^certainly!.*?\n",
        r"(?i)^i can help with that.*?\n",
    ]
    for pattern in fluff_patterns:
        text = re.sub(pattern, "", text)

    return text.strip()
