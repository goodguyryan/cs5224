"""Summarise one item or build one week's digest, recording revisions and review status."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable, NoReturn

from .compose import compose_digest, render_body
from .model import RetryableError, is_retryable
from .review import DIGEST, get_record, item_record_id, next_revision, put_record, week_items
from .summarise import find_segment, summarise_segment

# Approved and rejected items keep their status until their content changes.
SETTLED = {"pending", "approved", "rejected"}

LoadDocument = Callable[[str], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _record_failure(table: Any, key: dict[str, Any], existing: dict[str, Any] | None,
                    revision: int, error: Exception) -> None:
    # Keep the last good fields for inspection; the failed status keeps them out of the digest.
    record = dict(existing or {**key, "created_at": _now()})
    record.update(status="failed", revision=revision, updated_at=_now(),
                  last_error=f"{type(error).__name__}: {error}"[:1000])
    put_record(table, record)


def _reraise(error: Exception) -> NoReturn:
    if is_retryable(error) and not isinstance(error, RetryableError):
        raise RetryableError(str(error)) from error
    raise error


def summarise_item(
    load_document: LoadDocument,
    processed_key: str,
    segment_id: str,
    *,
    week: str,
    table: Any,
    model: Any,
    model_check: bool = False,
) -> dict[str, Any]:
    """Skip an unchanged item; a changed one gets a new revision and goes back to pending."""

    key = {"week_id": week, "record_id": item_record_id(segment_id)}
    existing = get_record(table, week, key["record_id"])
    revision = next_revision(existing)
    try:
        document = load_document(processed_key)
        segment = find_segment(document, segment_id)
        content_hash = hashlib.sha256(segment["content_text"].encode("utf-8")).hexdigest()
        if existing and existing["status"] in SETTLED and existing.get("content_hash") == content_hash:
            return {"segment_id": segment_id, "status": "skipped", "revision": int(existing["revision"])}
        result = summarise_segment(document, segment, model, model_check=model_check)
    except Exception as error:
        _record_failure(table, {**key, "segment_id": segment_id, "s3_keys": [processed_key]},
                        existing, revision, error)
        _reraise(error)

    now = _now()
    put_record(table, {
        **key,
        "segment_id": segment_id,
        "status": "pending",
        "revision": revision,
        "content_hash": content_hash,
        "title": segment.get("title") or segment_id,
        "subtitle": segment.get("subtitle"),
        "sitting_dates": [document["sitting_date"]],
        "topic_tags": [result["topic"]],
        "hansard_urls": [document["source"]["public_url"]],
        "s3_keys": [processed_key],
        "raw_key": document["source"]["raw_key"],
        "source_sha256": document["source"]["sha256"],
        "source_locations": list(dict.fromkeys(
            f"{segment_id} ¶{claim['paragraph']}" for claim in result["claims"])),
        "summary": result["summary"],
        "claims": result["claims"],
        "flagged_claims": result["flagged_claims"],
        "model_id": model.model_id,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    })
    return {"segment_id": segment_id, "status": "pending", "revision": revision,
            "claims": len(result["claims"]), "flagged_claims": len(result["flagged_claims"])}


def build_week_digest(
    week: str,
    *,
    table: Any,
    model: Any,
) -> dict[str, Any]:
    """Return without a digest when the week has no usable items."""

    records = week_items(table, week)
    failed = sorted(record["segment_id"] for record in records if record["status"] == "failed")
    items = sorted(
        (record for record in records if record["status"] in {"pending", "approved"} and record.get("claims")),
        key=lambda record: (record["sitting_dates"][0], record["segment_id"]),
    )
    if not items:
        return {"week_id": week, "status": "no_items", "failed_items": failed}

    fingerprint = hashlib.sha256("\n".join(
        f"{item['segment_id']}:{item['revision']}:{item['content_hash']}" for item in items
    ).encode("utf-8")).hexdigest()
    existing = get_record(table, week, DIGEST)
    if existing and existing["status"] in SETTLED and existing.get("items_fingerprint") == fingerprint:
        return {"week_id": week, "status": "skipped", "revision": int(existing["revision"])}

    key = {"week_id": week, "record_id": DIGEST}
    revision = next_revision(existing)
    try:
        digest = compose_digest(week, items, model)
        digest["body"] = render_body(digest)
    except Exception as error:
        _record_failure(table, key, existing, revision, error)
        _reraise(error)

    now = _now()
    put_record(table, {
        **key,
        "status": "pending",
        "revision": revision,
        "items_fingerprint": fingerprint,
        "item_revisions": {item["segment_id"]: int(item["revision"]) for item in items},
        "failed_items": failed,
        "sitting_dates": [sitting["sitting_date"] for sitting in digest["sittings"]],
        "topic_tags": [section["topic"] for section in digest["sections"]],
        "hansard_urls": [sitting["hansard_url"] for sitting in digest["sittings"]],
        "s3_keys": list(dict.fromkeys(s3_key for item in items for s3_key in item["s3_keys"])),
        "source_locations": [location for item in digest["cited_items"] for location in item["locations"]],
        "model_id": model.model_id,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
        **digest,
    })
    return {"week_id": week, "status": "pending", "revision": revision,
            "word_count": digest["word_count"], "word_count_ok": digest["word_count_ok"],
            "failed_items": failed}
