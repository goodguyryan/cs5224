"""Check that each claim's quote and speakers appear in the Hansard passage it cites."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .model import parse_json_reply

MIN_QUOTE_WORDS = 4
HONORIFICS = {"mr", "ms", "mrs", "mdm", "miss", "dr", "prof", "professor", "assoc", "associate", "er"}

SUPPORT_SYSTEM = (
    "You check citations in summaries of Singapore's Hansard. "
    "Judge only from the passage given. Reply with JSON only."
)


def normalise(text: str) -> str:
    # Curly quotes, dashes and spacing differ between the model's copy and the source.
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def contains(passage: str, phrase: str) -> bool:
    phrase = normalise(phrase)
    return bool(phrase) and f" {phrase} " in f" {normalise(passage)} "


def speaker_forms(speaker: str) -> list[str]:
    """'The Minister for Health (Dr Lee)' can appear as written, as 'Dr Lee', or as 'Lee'."""

    outside = " ".join(re.sub(r"\([^()]*\)", " ", speaker).split())
    # Brackets hold a name after an office, but a constituency after a name; keep only names.
    inside = [text for text in re.findall(r"\(([^()]+)\)", speaker)
              if normalise(text).split()[:1] and normalise(text).split()[0] in HONORIFICS]
    forms = [speaker, outside, *inside]
    for form in list(forms):
        words = normalise(form).split()
        while words and words[0] in HONORIFICS:
            words.pop(0)
        if words:
            forms.append(" ".join(words))
    return forms


def speaker_in_text(speaker: str, text: str) -> bool:
    return any(contains(text, form) for form in speaker_forms(speaker))


def same_speaker(first: str, second: str) -> bool:
    return speaker_in_text(first, second) or speaker_in_text(second, first)


def claim_problems(claim: dict[str, Any], paragraphs: list[str], segment_text: str) -> list[str]:
    problems = []
    if not claim["text"]:
        problems.append("claim has no text")
    index = claim["paragraph"]
    if not isinstance(index, int) or not 1 <= index <= len(paragraphs):
        problems.append("cited paragraph does not exist")
    elif len(normalise(claim["quote"]).split()) < MIN_QUOTE_WORDS:
        problems.append("quote is too short to support the claim")
    elif not contains(paragraphs[index - 1], claim["quote"]):
        problems.append("quote not found in cited paragraph")
    if claim["type"] in {"question", "answer"} and not claim["speakers"]:
        problems.append(f"{claim['type']} has no speaker")
    for speaker in claim["speakers"]:
        if not speaker_in_text(speaker, segment_text):
            problems.append(f"speaker not in cited segment: {speaker}")
    return problems


def model_supports(model: Any, claim: dict[str, Any], passage: str) -> bool:
    speakers = ", ".join(claim["speakers"]) or "none"
    prompt = (
        f"Passage:\n{passage}\n\nClaim: {claim['text']}\nSpeakers credited: {speakers}\n\n"
        "Does the passage alone support the claim, including who it credits? "
        'Reply {"supported": true} or {"supported": false}.'
    )
    return parse_json_reply(model.complete(SUPPORT_SYSTEM, prompt, max_tokens=50)).get("supported") is True


def check_claims(
    claims: list[dict[str, Any]],
    paragraphs: list[str],
    segment_text: str,
    model: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split claims into supported and flagged; the model check runs only if given a model."""

    supported, flagged = [], []
    for claim in claims:
        problems = claim_problems(claim, paragraphs, segment_text)
        if not problems and model is not None:
            if not model_supports(model, claim, paragraphs[claim["paragraph"] - 1]):
                problems.append("model check: passage does not support the claim")
        if problems:
            flagged.append({**claim, "problems": problems})
        else:
            supported.append(claim)
    return supported, flagged
