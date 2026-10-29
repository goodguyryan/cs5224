"""Ask Bedrock for one segment's claims, then keep only those its own text supports."""

from __future__ import annotations

from typing import Any

from .citations import check_claims
from .model import ModelOutputError, parse_json_reply

TOPICS = {
    "budget": "Budget and public finance",
    "economy": "Economy and jobs",
    "cost_of_living": "Cost of living",
    "housing": "Housing",
    "transport": "Transport",
    "health": "Health",
    "education": "Education",
    "social": "Families and social support",
    "security": "Defence and security",
    "law": "Law and home affairs",
    "foreign": "Foreign affairs",
    "environment": "Environment and climate",
    "digital": "Digital and technology",
    "parliament": "Parliamentary business",
    "other": "Other matters",
}
CLAIM_TYPES = ("question", "answer", "decision", "statement")
CLAIM_LABELS = {"question": "Question", "answer": "Answer", "decision": "Decision", "statement": "Point"}
MAX_CLAIMS = 8

SYSTEM = f"""You summarise one segment of Singapore's Hansard, the official report of Parliament, for a weekly public digest.

Use only the segment text you are given. Do not add background, figures, names or outcomes from anywhere else.

Write up to {MAX_CLAIMS} claims. Each claim is one plain sentence with exactly one type:
- question: what a Member asked or raised
- answer: what a Minister or other Member said in reply
- decision: what the House did, such as reading a Bill a second time, passing a motion, or a division result
- statement: another substantive point made in a speech or written answer
Keep a question and its answer as separate claims. Never fold an answer into a question.

For every claim give:
- speakers: the people who made the point, named exactly as the text names them, including any office in the text. Leave it empty only for decisions of the House.
- paragraph: the [¶n] number the claim comes from
- quote: 5 to 30 words copied exactly from that paragraph that support the claim

Leave out anything you cannot back with an exact quote. If the segment is procedural or has nothing substantive, return no claims.

Choose one topic key: {", ".join(TOPICS)}.

Reply with JSON only, in this shape:
{{"topic": "health", "claims": [{{"type": "question", "speakers": ["..."], "text": "...", "paragraph": 1, "quote": "..."}}]}}"""


class ItemError(ValueError):
    """The requested item cannot be summarised; retrying the same input will not help."""


def find_segment(document: dict[str, Any], segment_id: str) -> dict[str, Any]:
    for segment in document["segments"]:
        if segment["local_segment_id"] == segment_id:
            return segment
    raise ItemError(f"{segment_id} is not in sitting {document['sitting_id']}")


def paragraphs(segment: dict[str, Any]) -> list[str]:
    # The parser joins source blocks with blank lines; those blocks are the citable paragraphs.
    return [text for text in segment["content_text"].split("\n\n") if text.strip()]


def build_prompt(document: dict[str, Any], segment: dict[str, Any]) -> str:
    heading = " - ".join(filter(None, (segment.get("title"), segment.get("subtitle"))))
    numbered = "\n\n".join(f"[¶{index}] {text}" for index, text in enumerate(paragraphs(segment), 1))
    return (
        f"Sitting date: {document['sitting_date']}\n"
        f"Segment ID: {segment['local_segment_id']}\n"
        f"Heading: {heading or 'none'}\n"
        f"Section type: {segment.get('section_type') or 'none'}\n\n"
        f"Text, paragraphs numbered:\n\n{numbered}"
    )


def _paragraph_number(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lstrip("¶").isdigit():
        return int(value.strip().lstrip("¶"))
    return None


def parse_summary(reply: str) -> tuple[str, list[dict[str, Any]]]:
    value = parse_json_reply(reply)
    claims = value.get("claims")
    if not isinstance(claims, list) or not all(isinstance(claim, dict) for claim in claims):
        raise ModelOutputError("claims must be a list of objects")
    topic = value.get("topic") if value.get("topic") in TOPICS else "other"
    parsed = []
    for claim in claims[:MAX_CLAIMS]:
        speakers = claim.get("speakers") or []
        if isinstance(speakers, str):
            speakers = [speakers]
        parsed.append({
            "type": claim.get("type") if claim.get("type") in CLAIM_TYPES else "statement",
            "speakers": [str(name).strip() for name in speakers if str(name).strip()],
            "text": str(claim.get("text") or "").strip(),
            "paragraph": _paragraph_number(claim.get("paragraph")),
            "quote": str(claim.get("quote") or "").strip(),
        })
    return topic, parsed


def render_summary(segment_id: str, claims: list[dict[str, Any]]) -> str:
    ordered = sorted(claims, key=lambda claim: CLAIM_TYPES.index(claim["type"]))
    return "\n".join(
        f"{CLAIM_LABELS[claim['type']]}: {claim['text']} [{segment_id} ¶{claim['paragraph']}]"
        for claim in ordered
    )


def summarise_segment(
    document: dict[str, Any],
    segment: dict[str, Any],
    model: Any,
    *,
    model_check: bool = False,
) -> dict[str, Any]:
    reply = model.complete(SYSTEM, build_prompt(document, segment), max_tokens=2048)
    topic, claims = parse_summary(reply)
    supported, flagged = check_claims(
        claims, paragraphs(segment), segment["content_text"], model if model_check else None,
    )
    return {
        "topic": topic,
        "claims": supported,
        "flagged_claims": flagged,
        "summary": render_summary(segment["local_segment_id"], supported),
    }
