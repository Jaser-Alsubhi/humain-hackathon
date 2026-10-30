"""Break the stack on purpose, for the live demo. The monitor (python -m recovery.watch) should notice and fix it.
python -m recovery.break_it --list
python -m recovery.break_it <scenario>
python -m recovery.break_it --reset      restore a healthy stack. Run it only while the monitor is stopped."""
import sys

from recovery import faults_extra, scenarios, silent, unfixable


def names():
    return list(scenarios.NAMES) + silent.names() + list(unfixable.TARGET) + list(faults_extra.EXTRA)


def main(argv):
    if not argv or argv[0] == "--list":
        print("\n".join(names()))
        return 0
    if argv[0] == "--reset":
        print("reset:", scenarios.reset())
        return 0
    if argv[0] not in names():
        print("unknown scenario. Choose one of: " + ", ".join(names()))
        return 1
    scenarios.inject(argv[0])
    print("fault injected. The monitor should notice it within about 10 seconds.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
