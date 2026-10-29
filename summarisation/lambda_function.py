"""Step Functions -> Lambda entry points for summaries and digests. Importing this file makes no AWS calls."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from digest.model import BedrockModel
from digest.pipeline import build_week_digest, summarise_item
from digest.weeks import previous_week, week_dates

SINGAPORE = timezone(timedelta(hours=8))


def _s3():
    import boto3

    return boto3.client("s3", region_name=os.environ["AWS_REGION"])


def _review_table():
    import boto3

    return boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"]).Table(os.environ["REVIEW_TABLE"])


def _model():
    import boto3
    from botocore.config import Config

    # A full digest can take longer than the SDK's default 60-second read timeout.
    client = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"],
                          config=Config(read_timeout=300, retries={"max_attempts": 2}))
    return BedrockModel(client, os.environ["BEDROCK_INFERENCE_PROFILE"], os.environ["BEDROCK_MODEL_ID"])


def _loader(s3):
    def load(key):
        body = s3.get_object(Bucket=os.environ["PROCESSED_BUCKET"], Key=key)["Body"]
        try:
            return json.loads(body.read().decode("utf-8"))
        finally:
            body.close()
    return load


def _exists(s3, key):
    try:
        s3.head_object(Bucket=os.environ["PROCESSED_BUCKET"], Key=key)
    except Exception as error:
        # As in the scraper's store: only a real 404 means missing, never a 403.
        response = getattr(error, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or (status == 404 and code != "NoSuchBucket"):
            return False
        raise
    return True


def list_items_handler(event, context):
    """Return the week's segments for a Map state. Scheduled runs use the previous week."""
    event = event or {}
    week = event.get("week") or previous_week(datetime.now(SINGAPORE).date())
    s3 = _s3()
    load = _loader(s3)
    sittings, items = [], []
    for day in week_dates(week):
        key = f"processed/sittings/{day.isoformat()}.json"
        if not _exists(s3, key):
            continue
        document = load(key)
        sittings.append(document["sitting_date"])
        items.extend(
            {"week": week, "processed_key": key, "segment_id": segment["local_segment_id"]}
            for segment in document["segments"] if segment["content_text"].strip()
        )
    print(json.dumps({"week": week, "sittings": sittings, "item_count": len(items)}))
    return {"week": week, "sittings": sittings, "items": items}


def summarise_item_handler(event, context):
    result = summarise_item(
        _loader(_s3()), event["processed_key"], event["segment_id"],
        week=event["week"], table=_review_table(), model=_model(),
        model_check=os.environ.get("CITATION_MODEL_CHECK") == "true",
    )
    print(json.dumps(result))
    return result


def build_digest_handler(event, context):
    result = build_week_digest(
        event["week"], table=_review_table(), model=_model(), load_document=_loader(_s3()),
    )
    print(json.dumps(result))
    return result
