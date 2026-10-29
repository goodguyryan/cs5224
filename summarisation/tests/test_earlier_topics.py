import unittest

import fakes
from fakes import PROCESSED_KEY, SEGMENT_ID, WEEK, FakeModel
from digest.pipeline import build_week_digest, summarise_item
from digest.review import LocalReviewTable, get_record


def earlier_digest(title, topic="health", status="approved"):
    return {"week_id": "2026-W39", "record_id": "DIGEST", "status": status, "revision": 1,
            "cited_items": [{"ref": 1, "segment_id": "2026-09-22/takesSectionVOList/0007",
                             "title": title, "topic": topic}]}


class EarlierTopicTests(unittest.TestCase):
    def build(self, earlier, text=None):
        table = LocalReviewTable()
        table.put_item(earlier)
        document = fakes.sitting(text)
        summarise_item(lambda key: document, PROCESSED_KEY, SEGMENT_ID, week=WEEK, table=table,
                       model=FakeModel(fakes.ITEM_REPLY))
        build_week_digest(WEEK, table=table, model=FakeModel(fakes.digest_reply()),
                          load_document=lambda key: document)
        return get_record(table, WEEK, "DIGEST")

    def test_links_when_the_earlier_heading_is_in_the_original_passage(self):
        text = fakes.sitting()["segments"][0]["content_text"] + \
            "\n\nThis follows the Specialist Clinic Review announced last month."
        digest = self.build(earlier_digest("Specialist Clinic Review"), text)
        self.assertEqual(digest["sections"][0]["earlier"], [{
            "week_id": "2026-W39", "title": "Specialist Clinic Review",
            "segment_id": "2026-09-22/takesSectionVOList/0007", "matched_segment_id": SEGMENT_ID}])
        self.assertIn("Earlier coverage: Specialist Clinic Review also featured in Parliament in Five "
                      "for the week of 21 September 2026.", digest["body"])

    def test_links_a_returning_heading(self):
        digest = self.build(earlier_digest("Clinic Waiting Times"))
        self.assertEqual(digest["sections"][0]["earlier"][0]["title"], "Clinic Waiting Times")

    def test_no_link_from_topic_alone_or_from_unapproved_digests(self):
        for earlier in (earlier_digest("Hospital Bed Shortage"),
                        earlier_digest("Clinic Waiting Times", status="pending"),
                        earlier_digest("Clinic Waiting Times", topic="transport")):
            digest = self.build(earlier)
            self.assertNotIn("earlier", digest["sections"][0])
            self.assertNotIn("Earlier coverage", digest["body"])


if __name__ == "__main__":
    unittest.main()
