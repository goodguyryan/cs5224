"""Inspect a saved sitting without HTTP requests or file writes."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from hansard.parser import parse_sitting  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path,
                        default=PROJECT_ROOT / "data/raw/sittings/2026-10-06.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    document = parse_sitting(args.path.read_bytes())
    if args.json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return
    print(f"Sitting: {document['sitting_date']}")
    print(f"Segments: {document['segment_count']}")
    print(f"Official report: {document['source']['public_url']}")
    print(f"Raw SHA-256: {document['source']['sha256']}")
    print(f"Collections: {document['collection_counts']}")
    print(f"Warnings: {document['warnings']}")
    for segment in document["segments"]:
        if segment["title"] == "Digital Infrastructure Bill":
            print(f"  {segment['local_segment_id']}: {len(segment['content_text'])} characters")


if __name__ == "__main__":
    main()
