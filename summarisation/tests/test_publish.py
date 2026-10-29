import json
import unittest

import fakes
from fakes import WEEK, FakeModel, FakeReaderTable, FakeS3
from digest.pipeline import build_week_digest, summarise_item
from digest.publish import decide
from digest.review import LocalReviewTable, get_record

BUCKET = "summary-bucket"


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.table = LocalReviewTable()
        for day in ("2026-10-06", "2026-10-08"):
            document = fakes.sitting(sitting_date=day)
            summarise_item(lambda key, document=document: document, f"processed/sittings/{day}.json",
                           document["segments"][0]["local_segment_id"], week=WEEK, table=self.table,
                           model=FakeModel(fakes.ITEM_REPLY))
        build_week_digest(WEEK, table=self.table, model=FakeModel(fakes.digest_reply()))
        self.s3 = FakeS3()
        self.reader = FakeReaderTable()

    def approve(self):
        return decide(WEEK, "approve", table=self.table, s3=self.s3, reader_table=self.reader,
                      bucket=BUCKET, release_date="2026-10-13")

    def test_approval_publishes_exactly_what_the_reader_reads(self):
        digest = self.approve()
        put = self.s3.puts[0]
        self.assertEqual((put["Bucket"], put["Key"]), (BUCKET, "summaries/digest-2026-W41.json"))
        summary = json.loads(put["Body"].decode("utf-8"))
        self.assertEqual(set(summary), {"title", "body"})
        self.assertIn("Sources\n6 October 2026: ", summary["body"])
        self.assertTrue(summary["body"].endswith("8 October 2026: "
                                                 "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=8-10-2026"))
        self.assertEqual(self.reader.items, [{
            "HansardReportSummaryId": "digest-2026-W41",
            "DateOfRelease": "2026-10-13",
            "ActualReportLink": "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=8-10-2026",
            "S3BucketLink": "s3://summary-bucket/summaries/digest-2026-W41.json",
        }])
        self.assertEqual(digest["status"], "approved")
        self.assertEqual(get_record(self.table, WEEK, "DIGEST")["published_revision"], 1)
        self.assertEqual(get_record(self.table, WEEK, "ITEM#2026-10-06/takesSectionVOList/0003")["status"],
                         "approved")

    def test_rejection_publishes_nothing(self):
        decide(WEEK, "reject", table=self.table)
        self.assertEqual(get_record(self.table, WEEK, "DIGEST")["status"], "rejected")
        self.assertEqual(get_record(self.table, WEEK, "ITEM#2026-10-06/takesSectionVOList/0003")["status"],
                         "pending")

    def test_only_a_pending_digest_can_be_decided(self):
        self.approve()
        with self.assertRaisesRegex(ValueError, "approved, not pending"):
            self.approve()
        with self.assertRaisesRegex(ValueError, "No digest"):
            decide("2026-W40", "reject", table=self.table)
        self.assertEqual(len(self.s3.puts), 1)


if __name__ == "__main__":
    unittest.main()
