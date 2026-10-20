"""Command-line entry point for the shared retrieval workflow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from hansard.client import HansardClient
from hansard.pipeline import run_window
from hansard.storage import LocalHansardStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True,
                        help="First sitting date, inclusive (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=date.fromisoformat, required=True,
                        help="Last sitting date, inclusive (YYYY-MM-DD)")
    parser.add_argument("--delay", type=float, default=1, help="Minimum seconds between HTTP requests")
    parser.add_argument("--retries", type=int, default=2, help="Maximum attempts per HTTP request")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data")
    args = parser.parse_args()
    try:
        summary = run_window(
            LocalHansardStore(args.data_root),
            HansardClient(delay=args.delay, retries=args.retries),
            from_date=args.from_date,
            to_date=args.to_date,
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
