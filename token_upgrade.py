import json
import re

def compress_prompt(text: str) -> str:
    """
    Advanced Token Minification for LLM Contexts.
    Performs lossless (or near-lossless) compression on context payloads to drastically reduce API token usage.
    """
    if not text:
        return ""

    # 1. JSON Minification: Find JSON blocks and minify them.
    def minify_json_match(match):
        try:
            parsed = json.loads(match.group(1))
            minified = json.dumps(parsed, separators=(',', ':'))
            return minified
        except json.JSONDecodeError:
            return match.group(0)

    # Minify standard markdown JSON blocks
    text = re.sub(r'```json\s*(\{.*?\})\s*```', minify_json_match, text, flags=re.DOTALL)
    
    # 2. Code Block Minification (Python, JS, HTML, CSS)
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
            code = re.sub(r'^\s*\"\"\"[\s\S]*?\"\"\"', '', code, flags=re.MULTILINE)
            code = re.sub(r"^\s*'''[\s\S]*?'''", '', code, flags=re.MULTILINE)
            # Remove comments
            code = re.sub(r'#.*', '', code)
            # Remove blank lines
            code = re.sub(r'\n\s*\n', '\n', code)
            
        return f"```{lang}\n{code.strip()}\n```"

    # Match any code block
    text = re.sub(r'```(\w+)\s*\n([\s\S]*?)\n```', minify_code_match, text)

    # 3. Markdown / Structural Collapse
    # Remove multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove trailing spaces on lines
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    
    # 4. Filler Phrase Stripping (Only safe conversational fluff)
    fluff_patterns = [
        r"(?i)^here is the .*?:?\s*\n",
        r"(?i)^certainly!.*?\n",
        r"(?i)^i can help with that.*?\n",
    ]
    for pattern in fluff_patterns:
        text = re.sub(pattern, "", text)

    return text.strip()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            content = f.read()
        print(compress_prompt(content))
