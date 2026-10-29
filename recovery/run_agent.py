"""Run the agent against injected faults: python -m recovery.run_agent [scenario|all] [--dry-run]"""
import sys
import time

from recovery import agent, scenarios


def main():
    words = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    names = scenarios.NAMES if not words or words[0] == "all" else [words[0]]
    rows = []
    for name in names:
        print("\n==", name)
        print("   reset:", scenarios.reset())
        scenarios.inject(name)
        time.sleep(6)
        r = agent.run(name, dry_run=dry)
        rows.append(r)
        print("   recovered=%s steps=%d actions=%d verified=%s seconds=%.0f tokens=%d" % (
            r["recovered"], r["steps"], r["actions"], r["verified"], r["seconds"], r["tokens"]))
        print("   summary:", agent._ascii(r["final"]).replace("\n", " ")[:300])
        print("   audit:", r["audit"])
    scenarios.reset()
    print("\nSUMMARY")
    for r in rows:
        print("  %-11s recovered=%s steps=%2d actions=%d verified=%s %3.0fs" % (
            r["scenario"], r["recovered"], r["steps"], r["actions"], r["verified"], r["seconds"]))


if __name__ == "__main__":
    main()
