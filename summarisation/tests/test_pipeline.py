import unittest

import fakes
from fakes import PROCESSED_KEY, SEGMENT_ID, WEEK, FakeModel, ClientError
from digest.model import ModelOutputError, RetryableError
from digest.pipeline import build_week_digest, summarise_item
from digest.review import LocalReviewTable, get_record, week_items


def summarise(table, model, document=None):
    document = document or fakes.sitting()
    return summarise_item(lambda key: document, PROCESSED_KEY, SEGMENT_ID,
                          week=WEEK, table=table, model=model)


class SummariseItemTests(unittest.TestCase):
    def test_writes_a_pending_record_with_checked_claims(self):
        table = LocalReviewTable()
        result = summarise(table, FakeModel(fakes.ITEM_REPLY))
        self.assertEqual(result, {"segment_id": SEGMENT_ID, "status": "pending", "revision": 1,
                                  "claims": 3, "flagged_claims": 1})
        record = get_record(table, WEEK, f"ITEM#{SEGMENT_ID}")
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["sitting_dates"], ["2026-10-06"])
        self.assertEqual(record["topic_tags"], ["health"])
        self.assertEqual(record["s3_keys"], [PROCESSED_KEY])
        self.assertEqual(record["hansard_urls"],
                         ["https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=6-10-2026"])
        self.assertEqual(record["source_locations"], [f"{SEGMENT_ID} ¶1", f"{SEGMENT_ID} ¶2", f"{SEGMENT_ID} ¶4"])
        self.assertEqual(record["flagged_claims"][0]["problems"], ["quote not found in cited paragraph"])
        self.assertIn(f"Answer: Dr Aaron Koh said the median wait fell from forty to thirty-two days. "
                      f"[{SEGMENT_ID} ¶2]", record["summary"])

    def test_unchanged_item_is_skipped_without_calling_the_model(self):
        table = LocalReviewTable()
        summarise(table, FakeModel(fakes.ITEM_REPLY))
        model = FakeModel(fakes.ITEM_REPLY)
        self.assertEqual(summarise(table, model)["status"], "skipped")
        self.assertEqual(model.calls, [])

    def test_changed_item_gets_a_new_revision_and_returns_to_pending(self):
        table = LocalReviewTable()
        summarise(table, FakeModel(fakes.ITEM_REPLY))
        record = get_record(table, WEEK, f"ITEM#{SEGMENT_ID}")
        table.put_item({**record, "status": "approved"})
        changed = fakes.sitting(fakes.sitting()["segments"][0]["content_text"] + "\n\nA correction.")
        result = summarise(table, FakeModel(fakes.ITEM_REPLY), changed)
        self.assertEqual((result["status"], result["revision"]), ("pending", 2))
        self.assertEqual(get_record(table, WEEK, f"ITEM#{SEGMENT_ID}")["status"], "pending")

    def test_throttling_marks_the_item_failed_and_raises_retryable(self):
        table = LocalReviewTable()
        with self.assertRaises(RetryableError):
            summarise(table, FakeModel(RetryableError("throttled")))
        record = get_record(table, WEEK, f"ITEM#{SEGMENT_ID}")
        self.assertEqual((record["status"], record["revision"]), ("failed", 1))
        self.assertIn("throttled", record["last_error"])
        # The next run retries the same revision.
        self.assertEqual(summarise(table, FakeModel(fakes.ITEM_REPLY))["revision"], 1)
        self.assertEqual(get_record(table, WEEK, f"ITEM#{SEGMENT_ID}")["status"], "pending")

    def test_transient_s3_error_is_retryable_and_bad_output_is_not(self):
        table = LocalReviewTable()

        def unavailable(key):
            raise ClientError("ServiceUnavailableException", 503)
        with self.assertRaises(RetryableError):
            summarise_item(unavailable, PROCESSED_KEY, SEGMENT_ID, week=WEEK, table=table, model=FakeModel("{}"))
        with self.assertRaises(ModelOutputError):
            summarise(table, FakeModel("not json"))
        self.assertEqual(get_record(table, WEEK, f"ITEM#{SEGMENT_ID}")["status"], "failed")


class WeekDigestTests(unittest.TestCase):
    def setUp(self):
        self.table = LocalReviewTable()
        summarise(self.table, FakeModel(fakes.ITEM_REPLY))

    def test_empty_week_creates_no_digest(self):
        table = LocalReviewTable()
        self.assertEqual(build_week_digest(WEEK, table=table, model=FakeModel("{}"))["status"], "no_items")
        self.assertEqual(table.records, {})

    def test_builds_pending_digest_with_citations_and_sources(self):
        result = build_week_digest(WEEK, table=self.table, model=FakeModel(fakes.digest_reply()))
        self.assertEqual((result["status"], result["revision"], result["word_count_ok"]), ("pending", 1, True))
        digest = get_record(self.table, WEEK, "DIGEST")
        self.assertEqual(digest["status"], "pending")
        self.assertEqual(digest["title"], "Parliament in Five: week of 5 October 2026")
        self.assertEqual(digest["topic_tags"], ["health"])
        self.assertEqual(digest["item_revisions"], {SEGMENT_ID: 1})
        body = digest["body"]
        self.assertTrue(body.startswith("Health\n\nMs Rina Lim asked about clinic waits"))
        self.assertIn("waiting [1]\n\nCited items\n[1] 6 October 2026, Clinic Waiting Times "
                      f"({SEGMENT_ID} ¶1, ¶2, ¶4)", body)
        self.assertTrue(body.endswith(
            "Sources\n6 October 2026: https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=6-10-2026"))

    def test_paragraphs_with_unknown_claims_are_dropped(self):
        reply = fakes.digest_reply(claims=("1.1", "9.9"))
        with self.assertRaises(ModelOutputError):
            build_week_digest(WEEK, table=self.table, model=FakeModel(reply))
        self.assertEqual(get_record(self.table, WEEK, "DIGEST")["status"], "failed")

    def test_word_count_outside_range_is_retried_once_then_flagged(self):
        model = FakeModel(fakes.digest_reply(400), fakes.digest_reply(500))
        result = build_week_digest(WEEK, table=self.table, model=model)
        self.assertEqual(len(model.calls), 2)
        self.assertIn("Your previous draft had 400 words", model.calls[1])
        self.assertEqual((result["word_count"], result["word_count_ok"]), (500, False))

    def test_unchanged_week_is_skipped_and_changed_item_reopens_review(self):
        build_week_digest(WEEK, table=self.table, model=FakeModel(fakes.digest_reply()))
        digest = get_record(self.table, WEEK, "DIGEST")
        self.table.put_item({**digest, "status": "approved"})
        self.assertEqual(build_week_digest(WEEK, table=self.table, model=FakeModel("{}"))["status"], "skipped")
        changed = fakes.sitting(fakes.sitting()["segments"][0]["content_text"] + "\n\nA correction.")
        summarise(self.table, FakeModel(fakes.ITEM_REPLY), changed)
        result = build_week_digest(WEEK, table=self.table, model=FakeModel(fakes.digest_reply()))
        self.assertEqual((result["status"], result["revision"]), ("pending", 2))

    def test_failed_items_stay_out_and_are_listed(self):
        other = "2026-10-07/takesSectionVOList/0003"
        with self.assertRaises(RetryableError):
            summarise_item(lambda key: fakes.sitting(sitting_date="2026-10-07"),
                           "processed/sittings/2026-10-07.json", other, week=WEEK,
                           table=self.table, model=FakeModel(RetryableError("throttled")))
        result = build_week_digest(WEEK, table=self.table, model=FakeModel(fakes.digest_reply()))
        self.assertEqual(result["failed_items"], [other])
        digest = get_record(self.table, WEEK, "DIGEST")
        self.assertEqual(digest["sitting_dates"], ["2026-10-06"])
        self.assertEqual(len(week_items(self.table, WEEK)), 2)

    def test_speaker_named_without_citation_is_flagged(self):
        reply = fakes.digest_reply(claims=("1.1",))
        build_week_digest(WEEK, table=self.table, model=FakeModel(reply))
        flags = get_record(self.table, WEEK, "DIGEST")["speaker_flags"]
        self.assertEqual({flag["speaker"] for flag in flags},
                         {"Dr Aaron Koh", "The Minister for Health (Dr Aaron Koh)"})


if __name__ == "__main__":
    unittest.main()
