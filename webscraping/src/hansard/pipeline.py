"""One retrieval workflow shared by the command line and Lambda."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .client import HansardClient
from .parser import canonical_json_bytes, parse_sitting
from .storage import Store


def run_window(
    store: Store,
    client: HansardClient,
    *,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    """Skip completed dates; resume raw-only dates; discover and fetch new ones."""

    if from_date > to_date:
        raise ValueError("from_date cannot be after to_date")
    summary: dict[str, Any] = {
        "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
        "processed": [], "skipped": [], "not_found": [], "failures": [],
    }
    day = from_date
    while day <= to_date:
        day_text = day.isoformat()
        raw_key = f"raw/sittings/{day_text}.json"
        processed_key = f"processed/sittings/{day_text}.json"
        try:
            if store.exists(processed_key):
                summary["skipped"].append(day_text)
            else:
                if store.exists(raw_key):
                    raw_bytes = store.read(raw_key)
                    status = "recovered"
                else:
                    if not client.has_sitting(day):
                        summary["not_found"].append(day_text)
                        day += timedelta(days=1)
                        continue
                    fetched = client.fetch_sitting(day)
                    raw_bytes = fetched.raw_bytes
                    store.write(raw_key, raw_bytes)
                    status = "downloaded"
                processed = parse_sitting(raw_bytes, requested_date=day_text)
                # One final write is the completion marker. A failed write leaves raw recoverable.
                store.write(processed_key, canonical_json_bytes(processed))
                summary["processed"].append({
                    "date": day_text, "status": status,
                    "segment_count": processed["segment_count"],
                    "key": processed_key, "warnings": processed["warnings"],
                })
        except Exception as error:
            summary["failures"].append({"date": day_text, "error": str(error)})
        day += timedelta(days=1)
    return summary
