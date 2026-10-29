import os
from pathlib import Path


def load_env():
    for line in Path(".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


load_env()
from src.llm import ask

provider = os.environ.get("LLM_PROVIDER")
print("provider:", provider, "| model:", os.environ.get("LLM_MODEL") or "(default)")
assert provider in ("openai", "anthropic"), "set LLM_PROVIDER in .env first"

key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
key = os.environ.get(key_name, "")
assert key and not key.startswith("<"), "put your real key in .env first"

print("1. real call:", ask("Reply with the single word OK.").strip()[:50])

os.environ[key_name] = "sk-bad-key"
try:
    ask("Reply with the single word BAD.")
    print("2. bad key: NO ERROR (unexpected)")
except Exception as e:
    print("2. bad key raised:", type(e).__name__,
          "| rag_answer would degrade:", isinstance(e, (RuntimeError, ValueError)))
