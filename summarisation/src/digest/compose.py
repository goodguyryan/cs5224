"""Write the weekly digest from checked item claims and render it as the reader's plain text."""

from __future__ import annotations

from typing import Any

from .citations import same_speaker, speaker_in_text
from .model import ModelOutputError, parse_json_reply
from .summarise import TOPICS
from .weeks import day_label, week_monday

MIN_WORDS, MAX_WORDS = 700, 900

DIGEST_SYSTEM = f"""You write "Parliament in Five", a weekly digest of Singapore's Parliament that takes about five minutes to read.

You are given numbered Hansard items. Each item has claims with IDs such as 3.2 that have already been checked against the official text. Use only these claims. Do not add facts, figures, names, reactions or background that are not in them.

Rules:
- Write {MIN_WORDS} to {MAX_WORDS} words in total. If the claims are too thin for that, write less; never pad with material that is not in the claims.
- Group paragraphs into sections by topic, using the topic keys given. Lead with the items that matter most to the public.
- Every paragraph lists the IDs of the claims it uses, and every sentence must come from those claims.
- Credit points to the speakers given in the claims. Keep questions, answers and decisions distinct: do not present a question as an answer, or a proposal as a decision.
- Plain text only: no Markdown, bullet points or headings inside paragraphs.

Reply with JSON only, in this shape:
{{"sections": [{{"topic": "health", "paragraphs": [{{"text": "...", "claims": ["1.1", "1.2"]}}]}}]}}"""


def claim_index(items: list[dict[str, Any]]) -> dict[str, tuple[int, dict[str, Any]]]:
    return {
        f"{number}.{position}": (number, claim)
        for number, item in enumerate(items, 1)
        for position, claim in enumerate(item["claims"], 1)
    }


def digest_prompt(items: list[dict[str, Any]]) -> str:
    lines = [f"Topic keys: {', '.join(TOPICS)}", "", "Items:"]
    for number, item in enumerate(items, 1):
        lines.append(f"[{number}] {day_label(item['sitting_dates'][0])} | {item['title']} | "
                     f"topic: {item['topic_tags'][0]}")
        for position, claim in enumerate(item["claims"], 1):
            speakers = ", ".join(claim["speakers"]) or "the House"
            lines.append(f"  {number}.{position} ({claim['type']}; {speakers}) {claim['text']}")
    return "\n".join(lines)


def parse_digest(
    reply: str, index: dict[str, tuple[int, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep paragraphs whose claim IDs all exist; merge repeated topics into one section."""

    sections = parse_json_reply(reply).get("sections")
    if not isinstance(sections, list) or not all(isinstance(section, dict) for section in sections):
        raise ModelOutputError("sections must be a list of objects")
    kept: dict[str, dict[str, Any]] = {}
    dropped = []
    for section in sections:
        topic = section.get("topic") if section.get("topic") in TOPICS else "other"
        for paragraph in section.get("paragraphs") or []:
            if not isinstance(paragraph, dict):
                continue
            text = str(paragraph.get("text") or "").strip()
            ids = [str(value) for value in paragraph.get("claims") or []]
            unknown = [value for value in ids if value not in index]
            if not text or not ids or unknown:
                problem = "cites unknown claims " + ", ".join(unknown) if unknown else "cites no claims"
                dropped.append({"topic": topic, "text": text, "problem": problem})
                continue
            kept.setdefault(topic, {"topic": topic, "paragraphs": []})["paragraphs"].append(
                {"text": text, "claims": ids})
    return list(kept.values()), dropped


def word_count(sections: list[dict[str, Any]]) -> int:
    return sum(len(paragraph["text"].split()) for section in sections for paragraph in section["paragraphs"])


def speaker_flags(
    sections: list[dict[str, Any]], index: dict[str, tuple[int, dict[str, Any]]],
) -> list[dict[str, str]]:
    """Flag a paragraph that names someone who is not a speaker in any claim it cites."""

    everyone = {speaker for _, claim in index.values() for speaker in claim["speakers"]}
    flags = []
    for section in sections:
        for paragraph in section["paragraphs"]:
            cited = [speaker for value in paragraph["claims"] for speaker in index[value][1]["speakers"]]
            for speaker in sorted(everyone):
                if speaker_in_text(speaker, paragraph["text"]) and not any(
                        same_speaker(speaker, other) for other in cited):
                    flags.append({"speaker": speaker, "text": paragraph["text"]})
    return flags


def _distance(count: int) -> int:
    return max(MIN_WORDS - count, count - MAX_WORDS, 0)


def compose_digest(week: str, items: list[dict[str, Any]], model: Any) -> dict[str, Any]:
    index = claim_index(items)
    prompt = digest_prompt(items)
    best = None
    for _ in range(2):
        request = prompt if best is None else (
            f"{prompt}\n\nYour previous draft had {best[2]} words. Write it again in "
            f"{MIN_WORDS} to {MAX_WORDS} words with the same rules, without adding anything "
            "that is not in the claims.")
        sections, dropped = parse_digest(model.complete(DIGEST_SYSTEM, request, max_tokens=4096), index)
        count = word_count(sections)
        if best is None or _distance(count) < _distance(best[2]):
            best = (sections, dropped, count)
        if not _distance(count):
            break
    sections, dropped, count = best
    if not sections:
        raise ModelOutputError("Digest has no paragraph that cites a known claim")

    # Number cited items in reading order; uncited items stay out of the reference list.
    cited = list(dict.fromkeys(
        value for section in sections for paragraph in section["paragraphs"] for value in paragraph["claims"]))
    references: dict[int, int] = {}
    for value in cited:
        references.setdefault(index[value][0], len(references) + 1)
    cited_items = []
    for number, reference in references.items():
        item = items[number - 1]
        numbers = list(dict.fromkeys(index[value][1]["paragraph"] for value in cited if index[value][0] == number))
        cited_items.append({
            "ref": reference, "segment_id": item["segment_id"], "title": item["title"],
            "sitting_date": item["sitting_dates"][0], "hansard_url": item["hansard_urls"][0],
            "s3_key": item["s3_keys"][0], "topic": item["topic_tags"][0],
            "paragraphs": numbers,
            "locations": [f"{item['segment_id']} ¶{number}" for number in numbers],
        })
    for section in sections:
        for paragraph in section["paragraphs"]:
            paragraph["refs"] = list(dict.fromkeys(references[index[value][0]] for value in paragraph["claims"]))

    sittings = {item["sitting_dates"][0]: item["hansard_urls"][0] for item in items}
    return {
        "title": f"Parliament in Five: week of {day_label(week_monday(week))}",
        "sections": sections,
        "cited_items": cited_items,
        "sittings": [{"sitting_date": day, "hansard_url": sittings[day]} for day in sorted(sittings)],
        "word_count": count,
        "word_count_ok": not _distance(count),
        "dropped_paragraphs": dropped,
        "speaker_flags": speaker_flags(sections, index),
    }


def render_body(digest: dict[str, Any]) -> str:
    """Plain text for the reader: blank lines separate paragraphs, single newlines stay as lines."""

    blocks = []
    for section in digest["sections"]:
        blocks.append(TOPICS[section["topic"]])
        for paragraph in section["paragraphs"]:
            blocks.append(paragraph["text"] + " " + "".join(f"[{ref}]" for ref in paragraph["refs"]))
        for link in section.get("earlier", []):
            blocks.append(f"Earlier coverage: {link['title']} also featured in Parliament in Five "
                          f"for the week of {day_label(week_monday(link['week_id']))}.")
    blocks.append("Cited items\n" + "\n".join(
        f"[{item['ref']}] {day_label(item['sitting_date'])}, {item['title']} "
        f"({item['segment_id']} {', '.join(f'¶{number}' for number in item['paragraphs'])})"
        for item in digest["cited_items"]))
    blocks.append("Sources\n" + "\n".join(
        f"{day_label(sitting['sitting_date'])}: {sitting['hansard_url']}" for sitting in digest["sittings"]))
    return "\n\n".join(blocks)
