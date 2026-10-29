import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import fakes
from fakes import PROCESSED_KEY, SEGMENT_ID, WEEK, FakeS3
from digest.review import LocalReviewTable, get_record

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ENVIRONMENT = {
    "AWS_REGION": "ap-southeast-1",
    "PROCESSED_BUCKET": "processed-bucket",
    "REVIEW_TABLE": "review-table",
    "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
    "BEDROCK_INFERENCE_PROFILE": "apac.amazon.nova-lite-v1:0",
}


class FakeBedrock:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.requests = []

    def converse(self, **request):
        self.requests.append(request)
        return {"output": {"message": {"content": [{"text": self.texts.pop(0)}]}}, "stopReason": "end_turn"}


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3({PROCESSED_KEY: json.dumps(fakes.sitting()).encode("utf-8")})
        self.table = LocalReviewTable()
        self.bedrock = FakeBedrock(fakes.ITEM_REPLY, fakes.digest_reply())
        clients = {"s3": self.s3, "bedrock-runtime": self.bedrock}
        boto3 = types.SimpleNamespace(
            client=lambda name, **options: clients[name],
            resource=lambda name, **options: types.SimpleNamespace(Table=lambda table_name: self.table),
        )
        config = types.SimpleNamespace(Config=lambda **options: options)
        patches = [
            mock.patch.dict(os.environ, ENVIRONMENT),
            mock.patch.dict(sys.modules, {"boto3": boto3, "botocore.config": config}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        import lambda_function
        self.handlers = lambda_function

    def test_list_summarise_and_digest(self):
        with mock.patch("builtins.print"):
            listed = self.handlers.list_items_handler({"week": WEEK}, None)
            self.assertEqual(listed, {"week": WEEK, "sittings": ["2026-10-06"], "items": [
                {"week": WEEK, "processed_key": PROCESSED_KEY, "segment_id": SEGMENT_ID}]})
            result = self.handlers.summarise_item_handler(listed["items"][0], None)
            self.assertEqual(result["status"], "pending")
            digest = self.handlers.build_digest_handler({"week": WEEK}, None)
            self.assertEqual(digest["status"], "pending")
        self.assertEqual(self.bedrock.requests[0]["modelId"], "apac.amazon.nova-lite-v1:0")
        self.assertEqual(get_record(self.table, WEEK, "DIGEST")["model_id"], "amazon.nova-lite-v1:0")

    def test_scheduled_run_lists_the_previous_week(self):
        today = self.handlers.datetime(2026, 10, 12, 9, tzinfo=self.handlers.SINGAPORE)
        with mock.patch.object(self.handlers, "datetime", wraps=self.handlers.datetime) as clock, \
                mock.patch("builtins.print"):
            clock.now.return_value = today
            self.assertEqual(self.handlers.list_items_handler({}, None)["week"], WEEK)


if __name__ == "__main__":
    unittest.main()
