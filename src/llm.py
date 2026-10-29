import hashlib
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()
CACHE_DIR = Path("results/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _call_provider(prompt, system, temperature):
    provider = os.getenv("LLM_PROVIDER", "mock")
    model = os.getenv("LLM_MODEL", "")
    timeout = float(os.getenv("LLM_TIMEOUT", "30"))
    if provider == "mock":
        return '{"answer": "mock"}'
    if provider == "openai":
        from openai import OpenAI
        r = OpenAI(timeout=timeout).chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return r.choices[0].message.content
    if provider == "anthropic":
        import anthropic
        r = anthropic.Anthropic(timeout=timeout).messages.create(
            model=model,
            max_tokens=1024,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def ask(prompt, system="You are a helpful assistant.", temperature=0.0,
        retries=3, use_cache=True):
    key = hashlib.sha256(json.dumps(
        [os.getenv("LLM_PROVIDER"), os.getenv("LLM_MODEL"),
         system, prompt, temperature]).encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.txt"
    if use_cache and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    last_error = None
    for attempt in range(retries):
        try:
            text = _call_provider(prompt, system, temperature)
            cache_file.write_text(text, encoding="utf-8")
            return text
        except Exception as e:
            last_error = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM failed after {retries} attempts: {last_error}")


def _strip_fences(text):
    t = text.strip()
    t = t.removeprefix("```json").removeprefix("```").removesuffix("```")
    return t.strip()


def ask_json(prompt, schema, **kwargs):
    text = ask(prompt + "\nReturn only valid JSON.", **kwargs)
    try:
        return schema.model_validate_json(_strip_fences(text))
    except ValidationError as err:
        kwargs["use_cache"] = False
        fix = ask(
            prompt + "\nYour last answer was invalid: " + str(err)
            + "\nReturn only valid JSON matching the schema.", **kwargs)
        return schema.model_validate_json(_strip_fences(fix))
