"""Step 1: can the chosen model diagnose a simulated incident using tools?"""
import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI


def load_env():
    for line in Path(".env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


def tool(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


SERVICE = {"service": {"type": "string", "enum": ["backend", "db", "frontend"]}}
TOOLS = [
    tool("check_health", "Check the health of every service."),
    tool("get_logs", "Read recent log lines of one service.", SERVICE, ["service"]),
    tool("get_metrics", "Read CPU, memory and connection metrics of one service.", SERVICE, ["service"]),
    tool("get_config_diff", "Show the most recent configuration change."),
    tool("restart_service", "Restart one service. Disruptive.", SERVICE, ["service"]),
    tool("rollback_config", "Roll the configuration back to the last known good version."),
]

SYSTEM = (
    "You are an on-call SRE agent. A system is failing. Investigate before acting, "
    "prefer the least disruptive fix, and verify with check_health after any fix. "
    "When the system is healthy, reply with a short summary naming the root cause."
)


class Sim:
    """Tiny simulated system. The real fault is a bad config change. Restarting does not help."""

    def __init__(self):
        self.fixed = False
        self.restarts = 0

    def run(self, name, a):
        s = a.get("service")
        if name == "check_health":
            if self.fixed:
                return {"backend": "healthy", "db": "healthy", "frontend": "healthy"}
            return {"backend": "unhealthy", "db": "healthy", "frontend": "degraded"}
        if name == "get_logs":
            if s == "backend":
                if self.fixed:
                    return ["INFO connected to MySQL at db:3306", "INFO listening on :8000"]
                return ["ERROR connect to MySQL failed: unknown host 'db-old'",
                        "ERROR request /items failed: database unavailable",
                        "ERROR connect to MySQL failed: unknown host 'db-old'"]
            if s == "db":
                return ["INFO ready for connections", "WARN slow query 1.2s on items"]
            return ["WARN upstream backend returned 502"]
        if name == "get_metrics":
            if s == "db":
                return {"cpu": "78%", "connections": "14/151", "memory": "61%"}
            if s == "backend":
                return {"cpu": "3%", "memory": "40%", "restarts_last_hour": 0}
            return {"cpu": "2%", "memory": "20%"}
        if name == "get_config_diff":
            return {"changed": "DB_HOST: db -> db-old", "note": "tidy env names", "age": "20 minutes ago"}
        if name == "restart_service":
            self.restarts += 1
            return {"restarted": s}
        if name == "rollback_config":
            self.fixed = True
            return {"rolled_back": True}
        return {"error": "unknown tool"}


def trial(client, model, max_steps=10):
    sim = Sim()
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Alert: users see 502 errors. Investigate and fix."}]
    used, final = [], ""
    for _ in range(max_steps):
        r = client.chat.completions.create(model=model, messages=msgs, tools=TOOLS, tool_choice="auto")
        m = r.choices[0].message
        if not m.tool_calls:
            final = m.content or ""
            break
        msgs.append({"role": "assistant", "content": m.content or "", "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in m.tool_calls]})
        for tc in m.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {}
            used.append(tc.function.name + (":" + args["service"] if "service" in args else ""))
            out = sim.run(tc.function.name, args)
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})
        time.sleep(1)
    low = final.lower()
    return {"recovered": sim.fixed, "steps": len(used), "restarts": sim.restarts,
            "cause_named": ("db-old" in low or "db_host" in low), "tools": used}


def main():
    load_env()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                    base_url=os.environ.get("OPENAI_BASE_URL") or None,
                    timeout=float(os.environ.get("LLM_TIMEOUT", "30")))
    model = os.environ["LLM_MODEL"]
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    results = []
    for i in range(1, n + 1):
        try:
            r = trial(client, model)
        except Exception as e:
            print("trial", i, "ERROR", type(e).__name__, getattr(e, "status_code", ""))
            continue
        results.append(r)
        print("trial", i, "recovered=%s steps=%d restarts=%d cause_named=%s" % (
            r["recovered"], r["steps"], r["restarts"], r["cause_named"]))
        print("   ", " > ".join(r["tools"]))
    ok = sum(r["recovered"] for r in results)
    print("model", model, "| recovered", ok, "of", n)


if __name__ == "__main__":
    main()
