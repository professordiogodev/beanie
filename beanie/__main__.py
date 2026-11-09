"""Run one service:  python -m beanie gateway|menu|orders|payments|notifications  (port: PORT or the default)."""

import os
import sys

import uvicorn

PORTS = {"gateway": 8000, "menu": 8001, "orders": 8002, "payments": 8003, "notifications": 8004}
HOST = "0.0.0.0"  # noqa: S104  (a service has to listen on all interfaces inside a container)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in PORTS:
        sys.exit(f"usage: python -m beanie {'|'.join(PORTS)}")
    name = sys.argv[1]
    uvicorn.run(
        f"beanie.{name}.main:create_app",
        factory=True,
        host=os.environ.get("HOST", HOST),
        port=int(os.environ.get("PORT", PORTS[name])),
    )


if __name__ == "__main__":
    main()
