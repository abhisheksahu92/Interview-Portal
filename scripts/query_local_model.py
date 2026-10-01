#!/usr/bin/env python3
"""CLI utility to query local Ollama models (deepseek-r1:7b and qwen2.5-coder:7b)."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request


def query_ollama(model: str, prompt: str, temperature: float = 0.2, num_ctx: int = 8192) -> str:
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_text = data.get("response", "")
            if model.startswith("deepseek-r1"):
                # Clean think tags if needed or keep them as reasoning
                pass
            return response_text
    except Exception as e:
        sys.stderr.write(f"Error querying Ollama ({model}): {e}\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Query local Ollama models.")
    parser.add_argument(
        "--model",
        choices=["deepseek-r1:7b", "qwen2.5-coder:7b"],
        default="deepseek-r1:7b",
        help="Ollama model to invoke",
    )
    parser.add_argument("--prompt", required=True, help="Prompt text or file path with @file")
    parser.add_argument("--strip-think", action="store_true", help="Strip <think>...</think> from output")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    args = parser.parse_args()

    prompt = args.prompt
    if prompt.startswith("@"):
        with open(prompt[1:], "r", encoding="utf-8") as f:
            prompt = f.read()

    output = query_ollama(args.model, prompt, temperature=args.temperature)
    if args.strip_think:
        output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
    print(output)


if __name__ == "__main__":
    main()
