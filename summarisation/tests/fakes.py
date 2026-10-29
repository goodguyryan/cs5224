"""Stand-ins for Bedrock, S3 and the reader table, plus a small processed sitting."""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SEGMENT_ID = "2026-10-06/takesSectionVOList/0003"
PROCESSED_KEY = "processed/sittings/2026-10-06.json"
WEEK = "2026-W41"


def sitting(text=None, sitting_date="2026-10-06"):
    day = sitting_date.split("-")
    return {
        "sitting_id": sitting_date,
        "sitting_date": sitting_date,
        "source": {
            "public_url": "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate="
                          f"{int(day[2])}-{int(day[1])}-{day[0]}",
            "raw_key": f"raw/sittings/{sitting_date}.json",
            "sha256": "0" * 64,
        },
        "segments": [{
            "local_segment_id": f"{sitting_date}/takesSectionVOList/0003",
            "source_position": {"collection": "takesSectionVOList", "index": 3},
            "title": "Clinic Waiting Times",
            "subtitle": None,
            "section_type": "OA",
            "report_type": None,
            "question_number": "1",
            "content_text": text or (
                "1 Ms Rina Lim asked the Minister for Health what is the median waiting time "
                "for a first appointment at public specialist clinics.\n\n"
                "The Minister for Health (Dr Aaron Koh): The median waiting time fell from "
                "forty days to thirty-two days over the past year.\n\n"
                "Ms Rina Lim (Example GRC): Will the Ministry publish waiting times for each clinic?\n\n"
                "Dr Aaron Koh: We will publish waiting times for each clinic from next year."
            ),
            "source_record": {},
        }],
        "warnings": [],
    }


ITEM_REPLY = json.dumps({"topic": "health", "claims": [
    {"type": "question", "speakers": ["Ms Rina Lim"], "paragraph": 1,
     "text": "Ms Rina Lim asked about waiting times at public specialist clinics.",
     "quote": "what is the median waiting time for a first appointment"},
    {"type": "answer", "speakers": ["The Minister for Health (Dr Aaron Koh)"], "paragraph": 2,
     "text": "Dr Aaron Koh said the median wait fell from forty to thirty-two days.",
     "quote": "fell from forty days to thirty-two days"},
    {"type": "answer", "speakers": ["Dr Aaron Koh"], "paragraph": 4,
     "text": "Dr Aaron Koh said waiting times for each clinic will be published from next year.",
     "quote": "We will publish waiting times for each clinic from next year"},
    {"type": "decision", "speakers": [], "paragraph": 4,
     "text": "The House approved a new clinic budget.",
     "quote": "The House approved a new clinic budget"},
]})


def digest_reply(words=720, claims=("1.1", "1.2", "1.3")):
    filler = " ".join(["waiting"] * (words - 12))
    return json.dumps({"sections": [{"topic": "health", "paragraphs": [
        {"text": f"Ms Rina Lim asked about clinic waits and Dr Aaron Koh replied. {filler}",
         "claims": list(claims)},
    ]}]})


class FakeModel:
    """Returns replies in order; a reply that is an exception is raised instead."""

    model_id = "amazon.nova-lite-v1:0"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, prompt, *, max_tokens=2048):
        self.calls.append(prompt)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


class ClientError(Exception):
    """Shaped like botocore's ClientError, which the code inspects but never imports."""

    def __init__(self, code, status=400):
        super().__init__(code)
        self.response = {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}


class FakeS3:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.puts = []

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError("NoSuchKey", 404)
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError("404", 404)
        return {}

    def put_object(self, **request):
        self.puts.append(request)


class FakeReaderTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)
