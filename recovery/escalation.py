"""Hand-off to a human. The escalate tool writes an incident ticket; handled() checks the ticket names the real cause."""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "results" / "escalations"
LAST = {"path": None}
# A deliberately simple check, not a judge: the ticket must name a credential or authentication problem.
CAUSE_WORDS = ("access denied", "authentication", "credential", "password", "denied for user")


def escalate(summary, findings, tried, recommendation):
    from recovery.agent import redact
    DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    ticket = {"time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
              "summary": summary, "findings": findings, "tried": tried, "recommendation": recommendation}
    ticket = {k: redact(str(v))[:1500] for k, v in ticket.items()}
    path = DIR / ("ESC-%s-%03d.json" % (time.strftime("%Y%m%dT%H%M%S", time.localtime(now)), now % 1 * 1000))
    path.write_text(json.dumps(ticket, indent=2), encoding="utf-8")
    LAST["path"] = str(path)
    return ("escalated: incident ticket %s created and a human has been notified. "
            "Your work on this incident is finished; do not take further actions." % path.name)


def handled(path):
    """True if a ticket exists and its summary or findings name a credential or authentication problem."""
    if not path:
        return False
    try:
        ticket = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    text = " ".join(str(ticket.get(k, "")) for k in ("summary", "findings")).lower()
    return any(word in text for word in CAUSE_WORDS)
