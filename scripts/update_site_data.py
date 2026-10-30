"""Embed the saved results (results/recovery_eval.json) into site/index.html so the tiles, tables and replay show the latest runs.
python scripts/update_site_data.py    Safe to run again."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "site" / "index.html"


def main():
    rows = [r for r in json.loads((ROOT / "results" / "recovery_eval.json").read_text(encoding="utf-8")) if "error" not in r]
    html = PAGE.read_text(encoding="utf-8")
    html, n = re.subn(r"var ROWS = \[.*?\];\n", lambda m: "var ROWS = " + json.dumps(rows, separators=(",", ":")) + ";\n",
                      html, count=1, flags=re.S)
    assert n == 1, "cannot find the ROWS data in the page"
    PAGE.write_text(html, encoding="utf-8")
    print("embedded %d runs into %s" % (len(rows), PAGE))


if __name__ == "__main__":
    main()
