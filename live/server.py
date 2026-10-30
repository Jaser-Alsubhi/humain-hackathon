"""Live demo server: a visitor breaks the stack, and the monitor and agent fix it while the page shows each step.
It only starts the same two commands you can run by hand (recovery.break_it and recovery.watch). Standard library only.
Runs on the VM next to the app: python live/server.py   (Caddy forwards /api/live/* to it).
Safety: a fixed list of faults, one run at a time, a cooldown, a per-visitor and a daily cap, and a kill switch:
create the file ops/LIVE_DISABLED to switch live mode off at once."""
import json
import os
import subprocess  # nosec B404
import sys
import threading
import time
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
BIND = os.environ.get("LIVE_BIND", "172.17.0.1")
PORT = int(os.environ.get("LIVE_PORT", "8100"))
DOMAIN = os.environ.get("LIVE_DOMAIN", "mend-ai.swedencentral.cloudapp.azure.com")
DAILY_CAP = int(os.environ.get("LIVE_DAILY_CAP", "25"))
PER_IP_HOUR, COOLDOWN, RUN_LIMIT = 3, 20, 300
KILL = ROOT / "ops" / "LIVE_DISABLED"
COUNTS = ROOT / "results" / "live_counts.json"
SCENARIOS = {
    "db_down": "The database stops",
    "bad_config": "A bad configuration is deployed",
    "hung_backend": "The backend freezes, but Docker still says it is running",
    "silent_drop_payments": "Payments are accepted but silently lost",
    "sync_corruption": "A sync job turns good records bad",
    "queue_overflow": "Messages are lost during a traffic spike",
}
LOCK = threading.RLock()
RUN = {"state": "idle", "scenario": None, "events": [], "recovered": None, "started": 0.0, "ended": 0.0}
NEEDS_RESET = [False]
IP_HITS = {}


def today_count():
    try:
        d = json.loads(COUNTS.read_text(encoding="utf-8"))
        return int(d["count"]) if d.get("date") == date.today().isoformat() else 0
    except (OSError, ValueError, KeyError):
        return 0


def bump():
    COUNTS.parent.mkdir(exist_ok=True)
    COUNTS.write_text(json.dumps({"date": date.today().isoformat(), "count": today_count() + 1}), encoding="utf-8")


def add(text):
    with LOCK:
        RUN["events"].append({"t": round(time.time() - RUN["started"], 1), "text": str(text)[:240]})


def healthy():
    try:
        with urllib.request.urlopen("http://localhost:8000/ready", timeout=5) as r:  # nosec B310
            return r.status == 200
    except Exception:
        return False


def pump(proc):
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            add(line)


def worker(scenario):
    py = [sys.executable, "-u", "-m"]
    try:
        if NEEDS_RESET[0] or not healthy():
            add("Getting the stack back to a healthy start...")
            subprocess.run(py + ["recovery.break_it", "--reset"], cwd=ROOT, timeout=240, capture_output=True)  # nosec B603
            NEEDS_RESET[0] = False
        mon = subprocess.Popen(py + ["recovery.watch", "--once"], cwd=ROOT, stdout=subprocess.PIPE,  # nosec B603
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=pump, args=(mon,), daemon=True).start()
        end = time.time() + 30
        while time.time() < end and not any("monitor started" in e["text"] for e in RUN["events"]):
            time.sleep(0.3)
        add("Fault chosen: %s. Nobody tells the monitor what broke." % SCENARIOS[scenario])
        subprocess.run(py + ["recovery.break_it", scenario], cwd=ROOT, timeout=180, capture_output=True)  # nosec B603
        add("Fault injected.")
        try:
            rc = mon.wait(timeout=RUN_LIMIT)
        except subprocess.TimeoutExpired:
            mon.kill()
            rc = -9
            add("Stopped: the time limit for a live run was reached.")
        time.sleep(1)
        with LOCK:
            RUN["recovered"] = rc == 0
        NEEDS_RESET[0] = rc != 0
    except Exception as e:  # keep the server alive whatever happens
        add("Server error: %s" % type(e).__name__)
        NEEDS_RESET[0] = True
        with LOCK:
            RUN["recovered"] = False
    finally:
        with LOCK:
            RUN["state"], RUN["ended"] = "done", time.time()


def try_start(scenario, ip, now=None):
    """Returns (http status, message). Starts a run only when every limit allows it."""
    now = now or time.time()
    if scenario not in SCENARIOS:
        return 400, "Unknown fault."
    if KILL.exists():
        return 503, "Live mode is switched off right now. The recorded replay still works."
    with LOCK:
        if RUN["state"] == "running":
            return 409, "Someone is running a fault right now. You can watch it here, then try again."
        if now - RUN["ended"] < COOLDOWN:
            return 429, "The stack is settling. Try again in a few seconds."
        if today_count() >= DAILY_CAP:
            return 429, "Today's live runs are used up. The recorded replay shows the same thing."
        hits = [t for t in IP_HITS.get(ip, []) if now - t < 3600]
        if len(hits) >= PER_IP_HOUR:
            return 429, "You have used your live runs for this hour. The recorded replay is still open."
        IP_HITS[ip] = hits + [now]
        bump()
        RUN.update(state="running", scenario=scenario, events=[], recovered=None, started=now, ended=0.0)
    threading.Thread(target=worker, args=(scenario,), daemon=True).start()
    return 200, "started"


def status(since):
    with LOCK:
        ev = RUN["events"][since:]
        wait = max(0, round(COOLDOWN - (time.time() - RUN["ended"]))) if RUN["state"] == "done" else 0
        return {"state": RUN["state"], "scenario": RUN["scenario"], "events": ev, "next": since + len(ev),
                "recovered": RUN["recovered"], "seconds": round((RUN["ended"] or time.time()) - RUN["started"], 1) if RUN["started"] else 0,
                "runs_left": max(0, DAILY_CAP - today_count()), "wait": wait, "enabled": not KILL.exists()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def visitor(self):
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/live/scenarios":
            self.send(200, {"enabled": not KILL.exists(), "scenarios": [{"id": k, "label": v} for k, v in SCENARIOS.items()]})
        elif u.path == "/api/live/status":
            try:
                since = max(0, int(parse_qs(u.query).get("since", ["0"])[0]))
            except ValueError:
                since = 0
            self.send(200, status(since))
        else:
            self.send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/live/break":
            return self.send(404, {"error": "not found"})
        origin = self.headers.get("Origin")
        if origin and not origin.endswith("//" + DOMAIN):
            return self.send(403, {"error": "Not allowed from this page."})
        try:
            size = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(size, 512)) or b"{}")
            scenario = str(body.get("scenario", ""))
        except (ValueError, AttributeError):
            return self.send(400, {"error": "Bad request."})
        code, msg = try_start(scenario, self.visitor())
        self.send(code, {"ok": code == 200, "message": msg})


def main():
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print("live server on %s:%d" % (BIND, PORT), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
