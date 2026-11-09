#!/usr/bin/env python3
"""Start all five services on localhost for development. Ctrl+C stops them.

python scripts/run_all.py            # gateway :8000, menu :8001, orders :8002, payments :8003, notifications :8004
"""

import os
import signal
import subprocess
import sys

SERVICES = {"gateway": 8000, "menu": 8001, "orders": 8002, "payments": 8003, "notifications": 8004}


def main() -> None:
    procs = []
    for name, port in SERVICES.items():
        env = {**os.environ, "PORT": str(port)}
        procs.append(subprocess.Popen([sys.executable, "-m", "beanie", name], env=env))  # noqa: S603
        print(f"started {name} on :{port} (pid {procs[-1].pid})", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        for p in procs:
            p.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
