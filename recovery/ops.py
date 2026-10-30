"""Real environment tools for the recovery agent: logs, health, actions and config."""
import difflib
import subprocess  # nosec B404
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops"
ACTIVE = OPS / "active.override.yml"
LKG = OPS / "lkg.override.yml"
BASE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "ops/active.override.yml"]
API = "http://localhost:8000"
SERVICES = ("backend", "db", "frontend")

CONFIG_TEMPLATE = """services:
  backend:
    environment:
      DATABASE_URL: mysql+pymysql://root:${{DB_PASSWORD:-devpassword}}@{host}:3306/hackdb
      OPS_CONFIG_VERSION: "{version}"
"""


def config_text(host="db", version="good", note=""):
    text = CONFIG_TEMPLATE.format(host=host, version=version)
    return ("# " + note + "\n" + text) if note else text


def write_config(path, text):
    OPS.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_config():
    if not ACTIVE.exists() or not LKG.exists():
        good = config_text()
        write_config(ACTIVE, good)
        write_config(LKG, good)


ensure_config()


def sh(args, timeout=120):
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,  # nosec B603
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout


def compose(*args, timeout=120):
    return sh(BASE + list(args), timeout)


def http(path, timeout=8):
    try:
        with urllib.request.urlopen(API + path, timeout=timeout) as r:  # nosec B310
            return r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, type(e).__name__


def _bad_service(service):
    return None if service in SERVICES else "unknown service, choose one of %s" % (SERVICES,)


# ---- observation tools -------------------------------------------------
def check_health():
    return {"health": http("/health"), "ready": http("/ready")}


def frozen_processes():
    """Processes inside the containers that are stopped (T), blocked (D) or zombies (Z), as (service, pid, command, state)."""
    found = []
    for svc in SERVICES:
        try:
            cid = compose("ps", "-q", svc)[1].strip()
            if not cid:
                continue
            rows = sh(["docker", "top", cid, "-eo", "pid,stat,comm"])[1].strip().splitlines()[1:]
        except Exception:
            continue
        for r in rows:
            parts = r.split(None, 2)
            if len(parts) == 3 and parts[1][:1] in ("T", "D", "Z"):
                found.append((svc, parts[0], parts[2], parts[1]))
    return found


def service_status():
    base = compose("ps", "--all", "--format", "{{.Service}}: {{.State}} ({{.Status}})")[1]
    extra = []
    for svc in ("backend", "db", "frontend"):
        try:
            cid = compose("ps", "-q", svc)[1].strip()
            if not cid:
                continue
            rows = sh(["docker", "top", cid, "-eo", "pid,stat,comm"])[1].strip().splitlines()[1:]
            states = "; ".join(" ".join(r.split()) for r in rows[:6])
            extra.append("%s processes (pid stat command): %s" % (svc, states))
        except Exception:
            pass
    if extra:
        extra.insert(0, "process STAT: S/R = normal, T = stopped (frozen), D = blocked on I/O, Z = zombie")
    warn = ["WARNING: %s has a frozen process, pid %s (%s) in state %s. The container reports running, but this process "
            "cannot answer requests." % f for f in frozen_processes()]
    return "\n".join(warn + [base] + extra)


def find_frozen_processes():
    """List processes inside the containers that are stopped (T), blocked (D) or zombies (Z)."""
    found = ["%s: pid %s (%s) is in state %s" % f for f in frozen_processes()]
    if found:
        return ("stopped, blocked or zombie processes found (T = stopped, D = blocked on I/O, Z = zombie). "
                "A container can report running while its process is frozen. Restart only the service that holds it:\n"
                + "\n".join(found))
    return "no stopped, blocked or zombie processes found"


def get_logs(service, tail=25):
    return _bad_service(service) or compose("logs", "--no-color", "--tail", str(tail), service)[1][-3000:]


def get_metrics():
    return sh(["docker", "stats", "--no-stream", "--format",
               "{{.Name}}: cpu={{.CPUPerc}} mem={{.MemUsage}}"])[1]


def config_changes():
    active = ACTIVE.read_text(encoding="utf-8").splitlines()
    good = LKG.read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(good, active, "last_known_good", "active", lineterm=""))
    return "\n".join(diff) if diff else "active config matches last known good"


# ---- action tools ------------------------------------------------------
def restart_service(service):
    return _bad_service(service) or compose("restart", service)[1][-300:]


def start_service(service):
    return _bad_service(service) or compose("start", service)[1][-300:]


def unpause_service(service):
    return _bad_service(service) or compose("unpause", service)[1][-300:]


def rollback_config():
    write_config(ACTIVE, LKG.read_text(encoding="utf-8"))
    rc, out = compose("up", "-d", "--no-deps", "backend")
    return "config rolled back, backend recreated" if rc == 0 else out[-500:]


# ---- waiting helpers ---------------------------------------------------
def wait_ready(seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        if http("/ready", timeout=5)[0] == 200:
            return True
        time.sleep(2)
    return False


def wait_db(seconds=90):
    end = time.time() + seconds
    while time.time() < end:
        if compose("ps", "db", "--format", "{{.Health}}")[1].strip() == "healthy":
            return True
        time.sleep(2)
    return False



DIRTY = OPS / "db_dirty.flag"


def mark_db_dirty():
    OPS.mkdir(exist_ok=True)
    DIRTY.write_text("1", encoding="utf-8")


def db_status():
    cmd = ("mysql -uroot -p\"$MYSQL_ROOT_PASSWORD\" -e "
           "\"SHOW VARIABLES LIKE 'max_connections'; SHOW STATUS LIKE 'Threads_connected'; SHOW PROCESSLIST\" 2>&1")
    return compose("exec", "-T", "db", "sh", "-c", cmd)[1][-1500:]


def dependencies(path=None):
    """service -> set of services it depends on, read from docker-compose.yml (no hand-written graph)."""
    deps, svc, in_dep = {}, None, False
    for raw in (path or ROOT / "docker-compose.yml").read_text(encoding="utf-8-sig").splitlines():
        line = raw.split("#")[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if indent == 0:
            svc, in_dep = None, False
        elif indent == 2 and text.endswith(":"):
            svc, in_dep = text[:-1], False
        elif indent == 4 and svc:
            in_dep = text == "depends_on:"
        elif in_dep and indent >= 6:
            if text.startswith("- "):
                deps.setdefault(svc, set()).add(text[2:].strip())
            elif indent == 6 and text.endswith(":"):
                deps.setdefault(svc, set()).add(text[:-1])
    return deps


def recreate_service(service):
    return _bad_service(service) or compose("up", "-d", "--force-recreate", "--no-deps", service)[1][-300:]
