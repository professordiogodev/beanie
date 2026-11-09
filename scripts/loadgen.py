#!/usr/bin/env python3
"""Send realistic traffic to the gateway so dashboards and traces have something to show. Standard library only.

python scripts/loadgen.py                       # 2 orders per second against http://localhost:8000, until Ctrl+C
python scripts/loadgen.py --rate 10 --seconds 60 --decline 0.1 --url http://gateway:8000
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request

ITEMS = ["espresso", "flat-white", "cappuccino", "cold-brew", "croissant"]


def order(url: str, decline: float) -> int:
    body = {
        "customer": random.choice(["Ana", "Bruno", "Carla", "Dina", "Eli"]),  # noqa: S311
        "items": [{"item_id": random.choice(ITEMS), "quantity": random.randint(1, 3)}],  # noqa: S311
        "card_token": "tok_declined" if random.random() < decline else "tok_visa",  # noqa: S311
    }
    req = urllib.request.Request(  # noqa: S310
        url + "/api/orders", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--rate", type=float, default=2.0, help="orders per second")
    ap.add_argument("--seconds", type=float, default=0, help="0 = until Ctrl+C")
    ap.add_argument("--decline", type=float, default=0.05, help="share of orders paid with a declined card")
    a = ap.parse_args()
    if not a.url.startswith(("http://", "https://")):
        raise SystemExit("--url must start with http:// or https://")
    counts: dict[int, int] = {}
    end = time.time() + a.seconds if a.seconds else None
    try:
        while end is None or time.time() < end:
            code = order(a.url, a.decline)
            counts[code] = counts.get(code, 0) + 1
            print(f"\r{dict(sorted(counts.items()))}", end="", flush=True)
            time.sleep(1 / a.rate)
    except KeyboardInterrupt:
        pass
    print()


if __name__ == "__main__":
    main()
