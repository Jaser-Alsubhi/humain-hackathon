"""Print whether each Groq model still has daily token allowance. python -m recovery.limits"""
import os

from openai import OpenAI

from recovery.agent import redact
from recovery.model_check import load_env

load_env()
c = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ.get("OPENAI_BASE_URL"), max_retries=0)
big = "status check " * 800
for model in ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]:
    try:
        c.chat.completions.create(model=model, messages=[{"role": "user", "content": big + "Reply OK."}], max_tokens=5)
        print(model, "OK, requests go through")
    except Exception as e:
        print(model, type(e).__name__, redact(str(e))[150:330])
