"""Turn one saved SPRS response into one understandable processed document."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

# Observed in the saved sitting, not a promise about every SPRS response.
TRANSCRIPT_COLLECTIONS = (
    "takesSectionVOList",
    "writtenAnswersVOList",
    "writtenAnsNAVOList",
)
SUPPORTING_COLLECTIONS = ("attendanceList", "ptbaList", "a2bList", "annexureList")
# These are PDF references to original-language speeches. Keep them in raw JSON only.
RAW_ONLY_COLLECTIONS = ("vernacularList",)
_BLOCK_TAGS = {
    "p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "blockquote", "table", "tr",
}


class SittingValidationError(ValueError):
    """The response is malformed, unsupported, or for a different date."""


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.current: list[str] = []
        self.ignored = 0

    def flush(self) -> None:
        text = " ".join("".join(self.current).split())
        self.current.clear()
        if text:
            self.blocks.append(text)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1
        elif not self.ignored and tag in _BLOCK_TAGS:
            self.flush()
        elif not self.ignored and tag in {"td", "th"}:
            self.current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)
        elif not self.ignored and tag in _BLOCK_TAGS:
            self.flush()

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.current.append(data)


def html_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n\n".join(filter(None, (html_to_text(item) for item in value)))
    if isinstance(value, dict):
        return "\n\n".join(filter(None, (html_to_text(item) for item in value.values())))
    parser = _TextParser()
    parser.feed(str(value))
    parser.close()
    parser.flush()
    return "\n\n".join(parser.blocks)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def parse_sitting_date(value: Any) -> str:
    if isinstance(value, str):
        for pattern in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), pattern).date().isoformat()
            except ValueError:
                pass
    raise SittingValidationError(f"Missing or invalid sitting date: {value!r}")


def full_report_public_url(sitting_date: str) -> str:
    day = date.fromisoformat(sitting_date)
    return ("https://sprs.parl.gov.sg/search/#/fullreport?sittingdate="
            f"{day.day}-{day.month}-{day.year}")


def validate_sitting(payload: Any, requested_date: str | None = None) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("metadata"), dict):
        raise SittingValidationError("Expected a full report with a metadata object")
    sitting_date = parse_sitting_date(payload["metadata"].get("sittingDate"))
    if requested_date is not None and parse_sitting_date(requested_date) != sitting_date:
        raise SittingValidationError(f"Requested {requested_date}, got {sitting_date}")
    if not isinstance(payload.get("takesSectionVOList"), list):
        raise SittingValidationError("Expected takesSectionVOList to be a list")
    for name in TRANSCRIPT_COLLECTIONS + SUPPORTING_COLLECTIONS + RAW_ONLY_COLLECTIONS:
        if payload.get(name) is not None and not isinstance(payload[name], list):
            raise SittingValidationError(f"{name} must be a list or null")
    return sitting_date


def _record_text(record: dict[str, Any]) -> str:
    parts = []
    for field in ("content", "htmlContent", "htmlFullContent", "reportContent"):
        if record.get(field):
            parts.append(html_to_text(record[field]))
            break
    for label, fields in (
        ("CLARIFICATION", ("clarificationTitle", "clarificationSubTitle", "clarificationText")),
        ("FOOTNOTES", ("footNotes",)),
        ("FOOTNOTE QUESTIONS", ("footNoteQuestions",)),
    ):
        text = "\n\n".join(filter(None, (html_to_text(record.get(f)) for f in fields)))
        if text:
            parts.append(label + "\n\n" + text)
    return "\n\n".join(filter(None, parts))


def parse_sitting(raw_bytes: bytes, requested_date: str | None = None) -> dict[str, Any]:
    """Keep one source hash; segment IDs are readable date/collection/index paths."""

    payload = json.loads(raw_bytes.decode("utf-8-sig"))
    sitting_date = validate_sitting(payload, requested_date)
    segments = []
    warnings = []
    known = set(TRANSCRIPT_COLLECTIONS + SUPPORTING_COLLECTIONS + RAW_ONLY_COLLECTIONS)
    collections = {name: value for name, value in payload.items() if isinstance(value, list)}
    for name, records in collections.items():
        if name not in known:
            warnings.append(f"Unrecognized collection {name}: {len(records)} records retained")

    for collection in TRANSCRIPT_COLLECTIONS:
        for index, record in enumerate(payload.get(collection) or []):
            if not isinstance(record, dict):
                raise SittingValidationError(f"{collection}[{index}] must be an object")
            segment_id = f"{sitting_date}/{collection}/{index:04d}"
            text = _record_text(record)
            if not text:
                warnings.append(f"No extracted text in {segment_id}; source_record retained")
            segments.append({
                "local_segment_id": segment_id,
                "source_position": {"collection": collection, "index": index},
                "title": record.get("title"),
                "subtitle": record.get("subTitle", record.get("subtitle")),
                "section_type": record.get("sectionType"),
                "report_type": record.get("reportType"),
                "question_number": record.get("questionNo"),
                "content_text": text,
                "source_record": deepcopy(record),
            })

    if not segments:
        raise SittingValidationError("Full report contains no transcript segments")
    return {
        "sitting_id": sitting_date,
        "sitting_date": sitting_date,
        "source": {
            "public_url": full_report_public_url(sitting_date),
            "raw_key": f"raw/sittings/{sitting_date}.json",
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        },
        "metadata": deepcopy(payload["metadata"]),
        "collection_counts": {name: len(records) for name, records in collections.items()},
        "supporting_collections": {
            name: deepcopy(records) for name, records in collections.items()
            if name not in TRANSCRIPT_COLLECTIONS and name not in RAW_ONLY_COLLECTIONS
        },
        "segment_count": len(segments),
        "segments": segments,
        "warnings": warnings,
    }
