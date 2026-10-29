"""Step 3 check: inject each fault, look at the signals, try the naive fix, reset."""
import time

from recovery import ops, scenarios


def show(label):
    print("  ", label, ops.check_health())
    print("  ", ops.service_status().replace("\n", " | "))


def main():
    print("reset:", scenarios.reset())
    show("healthy")
    for name in scenarios.NAMES:
        print("\n==", name)
        scenarios.inject(name)
        time.sleep(6)
        show("after fault")
        ops.restart_service("backend")
        time.sleep(10)
        print("   naive restart of backend fixed it:", ops.http("/ready", 8)[0] == 200)
        print("   reset ok:", scenarios.reset())


if __name__ == "__main__":
    main()
