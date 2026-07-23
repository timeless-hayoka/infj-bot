import os
import re
from pathlib import Path


def discover_inference(target_dir: str):
    print(f"Scanning {target_dir} for Inference and Prompt Assembly...\n")

    # Looking for LLM calls (OpenAI, local models, generate methods)
    llm_pattern = re.compile(
        r"\.generate\(|\.chat\.completions\.create|ChatCompletion|Ollama\(|requests\.post"
    )
    # Looking for where the system prompt is built
    prompt_pattern = re.compile(r"system_prompt\s*=|def build_prompt|messages\s*=\s*\[")

    found_llm = []
    found_prompts = []

    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if llm_pattern.search(line):
                                found_llm.append(
                                    f"{file_path}:{line_num} -> {line.strip()}"
                                )
                            if prompt_pattern.search(line):
                                found_prompts.append(
                                    f"{file_path}:{line_num} -> {line.strip()}"
                                )
                except Exception:
                    pass

    print("=== LLM INFERENCE CALLS FOUND ===")
    for call in found_llm:
        print(call)

    print("\n=== PROMPT ASSEMBLY FOUND ===")
    for call in found_prompts:
        print(call)


if __name__ == "__main__":
    target_directory = "/home/crexs/drift"
    if os.path.exists(target_directory):
        discover_inference(target_directory)
    else:
        print(f"[ERROR] Directory {target_directory} does not exist.")
