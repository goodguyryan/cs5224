"""Review records keyed by week, in DynamoDB or in memory with the same three operations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DIGEST = "DIGEST"
ITEM_PREFIX = "ITEM#"


def item_record_id(segment_id: str) -> str:
    return ITEM_PREFIX + segment_id


def get_record(table: Any, week: str, record_id: str) -> dict[str, Any] | None:
    response = table.get_item(Key={"week_id": week, "record_id": record_id}, ConsistentRead=True)
    return response.get("Item")


def put_record(table: Any, record: dict[str, Any]) -> None:
    table.put_item(Item=record)


def week_items(table: Any, week: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    start = None
    while True:
        request = {
            "KeyConditionExpression": "week_id = :week AND begins_with(record_id, :prefix)",
            "ExpressionAttributeValues": {":week": week, ":prefix": ITEM_PREFIX},
            "ConsistentRead": True,
        }
        if start:
            request["ExclusiveStartKey"] = start
        page = table.query(**request)
        items.extend(page.get("Items", []))
        start = page.get("LastEvaluatedKey")
        if not start:
            return items


def next_revision(existing: dict[str, Any] | None) -> int:
    """A failed attempt keeps its revision so the retry fills it; anything else moves on."""

    if existing is None:
        return 1
    if existing["status"] == "failed":
        return int(existing["revision"])
    return int(existing["revision"]) + 1


class LocalReviewTable:
    """Supports only the get_item, put_item and query calls made in this module."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, Any]] = {}

    def get_item(self, Key: dict[str, str], **_: Any) -> dict[str, Any]:
        record = self.records.get((Key["week_id"], Key["record_id"]))
        return {"Item": deepcopy(record)} if record else {}

    def put_item(self, Item: dict[str, Any]) -> None:
        self.records[(Item["week_id"], Item["record_id"])] = deepcopy(Item)

    def query(self, ExpressionAttributeValues: dict[str, str], **_: Any) -> dict[str, Any]:
        week, prefix = ExpressionAttributeValues[":week"], ExpressionAttributeValues[":prefix"]
        return {"Items": [
            deepcopy(record) for (record_week, record_id), record in sorted(self.records.items())
            if record_week == week and record_id.startswith(prefix)
        ]}
