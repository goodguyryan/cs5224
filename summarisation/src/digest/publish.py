"""Approve or reject a week's digest; approval writes exactly what the EC2 reader reads."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .review import DIGEST, get_record, put_record, week_items


def reader_id(week: str) -> str:
    return f"digest-{week}"


def publish_digest(digest: dict[str, Any], *, s3: Any, reader_table: Any, bucket: str,
                   release_date: str) -> dict[str, str]:
    """Upload the summary object before adding the archive row, as the reader's setup requires."""

    summary_id = reader_id(digest["week_id"])
    key = f"summaries/{summary_id}.json"
    # The reader rejects any field other than title and body.
    body = json.dumps({"title": digest["title"], "body": digest["body"]}, ensure_ascii=False)
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"),
                  ContentType="application/json; charset=utf-8")
    latest = max(digest["sittings"], key=lambda sitting: sitting["sitting_date"])
    row = {
        "HansardReportSummaryId": summary_id,
        "DateOfRelease": release_date,
        "ActualReportLink": latest["hansard_url"],
        "S3BucketLink": f"s3://{bucket}/{key}",
    }
    reader_table.put_item(Item=row)
    return row


def decide(week: str, decision: str, *, table: Any, s3: Any = None, reader_table: Any = None,
           bucket: str | None = None, release_date: str | None = None) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    digest = get_record(table, week, DIGEST)
    if digest is None:
        raise ValueError(f"No digest exists for {week}")
    if digest["status"] != "pending":
        raise ValueError(f"The {week} digest is {digest['status']}, not pending")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if decision == "reject":
        digest.update(status="rejected", reviewed_at=now)
        put_record(table, digest)
        return digest

    row = publish_digest(digest, s3=s3, reader_table=reader_table, bucket=bucket,
                         release_date=release_date)
    revisions = digest.get("item_revisions", {})
    for item in week_items(table, week):
        if item["status"] == "pending" and revisions.get(item["segment_id"]) == int(item["revision"]):
            item.update(status="approved", reviewed_at=now)
            put_record(table, item)
    digest.update(status="approved", reviewed_at=now, published_revision=digest["revision"],
                  published_reader_id=row["HansardReportSummaryId"],
                  published_s3_link=row["S3BucketLink"])
    put_record(table, digest)
    return digest
