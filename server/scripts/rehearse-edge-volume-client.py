#!/usr/bin/env python3
"""Generate the bounded external request fixture for D6 volume observation."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CONFIRMATION = "STAGING-D6-VOLUME-OBSERVE-REHEARSAL"
REQUEST_COUNT = 1_200
CONCURRENCY = 32
BASE_URL = "https://staging.bookpile.gal/"


def _request(index: int) -> int | str:
    request = Request(
        f"{BASE_URL}?d6_volume_observe={index}",
        headers={"User-Agent": "BOOKPILE-D6-volume-rehearsal/1"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status
    except HTTPError as error:
        return error.code
    except (TimeoutError, URLError):
        return "transport_error"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    arguments = parser.parse_args()
    if arguments.confirm != CONFIRMATION:
        parser.error(f"confirmation must be {CONFIRMATION}")

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        results = list(executor.map(_request, range(1, REQUEST_COUNT + 1)))
    elapsed = time.monotonic() - started
    counts = Counter(str(result) for result in results)
    payload = {
        "concurrency": CONCURRENCY,
        "elapsed_seconds": round(elapsed, 3),
        "privacy": "aggregate_only",
        "requests": REQUEST_COUNT,
        "status_counts": dict(sorted(counts.items())),
        "target": "staging_root",
    }
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if counts == {"200": REQUEST_COUNT} and elapsed < 60 else 1


if __name__ == "__main__":
    raise SystemExit(main())
