"""Show a week's pending digest with its citation checks, then approve or reject it."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from digest.publish import decide, reader_id
from digest.review import DIGEST, get_record, week_items


def report(digest: dict, items: list[dict]) -> str:
    claims = sum(len(item.get("claims", [])) for item in items)
    flagged = [(item["segment_id"], claim) for item in items for claim in item.get("flagged_claims", [])]
    lines = [
        f"Week {digest['week_id']}, digest revision {digest['revision']}, status {digest['status']}",
        f"Words: {digest['word_count']} (target 700-900{'' if digest['word_count_ok'] else ', OUTSIDE TARGET'})",
        f"Sittings: {', '.join(digest['sitting_dates'])}",
        "", "=" * 72, digest["title"], "", digest["body"], "=" * 72, "",
        "Citation check",
        f"  Item claims supported: {claims} of {claims + len(flagged)} across {len(items)} items",
    ]
    for segment_id, claim in flagged:
        lines.append(f"  Dropped claim in {segment_id}: {claim['text']!r}")
        lines.extend(f"      - {problem}" for problem in claim["problems"])
    for paragraph in digest.get("dropped_paragraphs", []):
        lines.append(f"  Dropped digest paragraph ({paragraph['problem']}): {paragraph['text'][:120]!r}")
    for flag in digest.get("speaker_flags", []):
        lines.append(f"  CHECK: names {flag['speaker']} without citing them: {flag['text'][:120]!r}")
    if digest.get("failed_items"):
        lines.append(f"  Failed items, not in this digest: {', '.join(digest['failed_items'])}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("week", help="ISO week, for example 2026-W41")
    parser.add_argument("--decision", choices=["approve", "reject"],
                        help="Skip the prompt, for example in a scripted review")
    args = parser.parse_args()
    import boto3

    dynamodb = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"])
    table = dynamodb.Table(os.environ["REVIEW_TABLE"])
    digest = get_record(table, args.week, DIGEST)
    if digest is None:
        parser.error(f"No digest exists for {args.week}")
    print(report(digest, week_items(table, args.week)))
    if digest["status"] != "pending":
        print(f"\nThe digest is {digest['status']}; only a pending digest can be reviewed.")
        return 1
    decision = args.decision
    while decision is None:
        answer = input("\nApprove and publish, reject, or quit? [a/r/q] ").strip().lower()
        if answer == "q":
            return 0
        decision = {"a": "approve", "r": "reject"}.get(answer)
    try:
        if decision == "reject":
            decide(args.week, "reject", table=table)
            print(f"Rejected {args.week}; nothing was published.")
            return 0
        decide(
            args.week, "approve", table=table, s3=boto3.client("s3", region_name=os.environ["AWS_REGION"]),
            reader_table=dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"]),
            bucket=os.environ["S3_SUMMARY_BUCKET"],
            release_date=datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
        )
    except ValueError as error:
        print(error)
        return 1
    print(f"Approved and published {args.week} as {reader_id(args.week)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
