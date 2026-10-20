"""Future EventBridge -> Lambda entry point. Importing this file makes no AWS calls."""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from hansard.client import HansardClient  
from hansard.pipeline import run_window
from hansard.storage import S3HansardStore


def event_dates(event):
    """Manual runs supply both dates; scheduled runs use a fixed 30-day range."""
    if "lookback" in event:
        raise ValueError("lookback was removed; supply from_date and to_date instead")
    if "from_date" in event or "to_date" in event:
        if "from_date" not in event or "to_date" not in event:
            raise ValueError("Supply both from_date and to_date")
        first = date.fromisoformat(event["from_date"])
        last = date.fromisoformat(event["to_date"])
    else:
        # Only the scheduler wrapper chooses a range; run_window always receives two dates.
        last = datetime.now(timezone(timedelta(hours=8))).date()
        first = last - timedelta(days=29)
    if first > last:
        raise ValueError("from_date cannot be after to_date")
    return first, last


def lambda_handler(event, context):
    event = event or {}
    from_date, to_date = event_dates(event)
    import boto3

    store = S3HansardStore(
        boto3.client("s3"), os.environ["RAW_BUCKET"], os.environ["PROCESSED_BUCKET"],
    )
    summary = run_window(store, HansardClient(), from_date=from_date, to_date=to_date)
    print(json.dumps(summary))
    if summary["failures"]:
        # Returning an error-shaped dictionary would count as a successful invocation.
        raise RuntimeError(f"Hansard retrieval failed for {len(summary['failures'])} date(s)")
    return summary
