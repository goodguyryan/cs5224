"""Run the summary pipeline on gold weeks and score it against reference key points."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from digest.citations import contains, same_speaker
from digest.compose import MAX_WORDS, MIN_WORDS
from digest.model import BedrockModel
from digest.pipeline import build_week_digest, summarise_item
from digest.review import DIGEST, LocalReviewTable, get_record, week_items


class ReplayModel:
    """Answers with the week's saved replies, so the pipeline runs without Bedrock."""

    model_id = "replay"

    def __init__(self, replies: dict) -> None:
        self.replies = replies

    def complete(self, system: str, prompt: str, *, max_tokens: int = 2048) -> str:
        for line in prompt.splitlines():
            if line.startswith("Segment ID: "):
                return json.dumps(self.replies["items"][line.removeprefix("Segment ID: ")])
        return json.dumps(self.replies["digest"])


def bedrock_model() -> BedrockModel:
    import boto3
    from botocore.config import Config

    client = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"],
                          config=Config(read_timeout=300, retries={"max_attempts": 2}))
    return BedrockModel(client, os.environ["BEDROCK_INFERENCE_PROFILE"], os.environ["BEDROCK_MODEL_ID"])


def share(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator else None


def evaluate_week(folder: Path, model) -> dict:
    reference = json.loads((folder / "reference.json").read_text(encoding="utf-8"))
    week = reference["week"]
    table = LocalReviewTable()
    load = lambda key: json.loads((folder / key).read_text(encoding="utf-8"))  # noqa: E731
    failures = []
    for path in sorted((folder / "processed/sittings").glob("*.json")):
        key = path.relative_to(folder).as_posix()
        for segment in load(key)["segments"]:
            if not segment["content_text"].strip():
                continue
            try:
                summarise_item(load, key, segment["local_segment_id"], week=week, table=table, model=model)
            except Exception as error:
                failures.append({"segment_id": segment["local_segment_id"], "error": str(error)})
    build_week_digest(week, table=table, model=model, load_document=load)
    digest = get_record(table, week, DIGEST)
    items = {item["segment_id"]: item for item in week_items(table, week)}

    supported = sum(len(item.get("claims", [])) for item in items.values())
    flagged = sum(len(item.get("flagged_claims", [])) for item in items.values())
    in_digest = in_items = attributed = correct = 0
    points = []
    for point in reference["key_points"]:
        claims = items.get(point["segment_id"], {}).get("claims", [])
        matching = [claim for claim in claims if all(contains(claim["text"], word) for word in point["keywords"])]
        # A point counts once one paragraph carries all its keywords, not scattered across the digest.
        covered = bool(digest) and any(all(contains(paragraph, word) for word in point["keywords"])
                                       for paragraph in digest["body"].split("\n\n"))
        in_digest += covered
        in_items += bool(matching)
        speaker_ok = None
        if point.get("speaker") and matching:
            attributed += 1
            speaker_ok = any(same_speaker(point["speaker"], name) for claim in matching for name in claim["speakers"])
            correct += speaker_ok
        points.append({"id": point["id"], "in_items": bool(matching), "in_digest": covered,
                       "speaker_correct": speaker_ok})
    total = len(reference["key_points"])
    return {
        "week": week,
        "key_point_coverage_digest": share(in_digest, total),
        "key_point_coverage_items": share(in_items, total),
        "claims_supported": share(supported, supported + flagged),
        "claims": {"supported": supported, "flagged": flagged},
        "speaker_attribution_accuracy": share(correct, attributed),
        "speaker_points_scored": attributed,
        "digest_word_count": digest["word_count"] if digest else 0,
        "digest_word_count_in_range": bool(digest) and MIN_WORDS <= digest["word_count"] <= MAX_WORDS,
        "key_points": points,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=PROJECT_ROOT / "gold")
    parser.add_argument("--replay", action="store_true",
                        help="Use each week's replay.json instead of calling Bedrock")
    args = parser.parse_args()
    model = None if args.replay else bedrock_model()
    results = []
    for folder in sorted(path for path in args.gold.iterdir() if (path / "reference.json").is_file()):
        if args.replay:
            model = ReplayModel(json.loads((folder / "replay.json").read_text(encoding="utf-8")))
        results.append(evaluate_week(folder, model))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if any(result["failures"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
