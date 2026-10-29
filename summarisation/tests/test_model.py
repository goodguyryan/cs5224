import unittest

from fakes import ClientError
from digest.model import BedrockModel, ModelOutputError, RetryableError, parse_json_reply
from digest.summarise import build_prompt, parse_summary, render_summary
import fakes


class FakeBedrock:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def converse(self, **request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response


def reply(text, stop="end_turn"):
    return {"output": {"message": {"content": [{"text": text}]}}, "stopReason": stop}


class BedrockModelTests(unittest.TestCase):
    def test_calls_the_inference_profile(self):
        client = FakeBedrock(reply("{}"))
        model = BedrockModel(client, "apac.amazon.nova-lite-v1:0", "amazon.nova-lite-v1:0")
        self.assertEqual(model.complete("system", "prompt", max_tokens=100), "{}")
        request = client.requests[0]
        self.assertEqual(request["modelId"], "apac.amazon.nova-lite-v1:0")
        self.assertEqual(request["system"], [{"text": "system"}])
        self.assertEqual(request["inferenceConfig"], {"maxTokens": 100, "temperature": 0})

    def test_throttling_is_retryable_and_validation_is_not(self):
        model = BedrockModel(FakeBedrock(error=ClientError("ThrottlingException")), "p", "m")
        with self.assertRaises(RetryableError):
            model.complete("s", "p")
        model = BedrockModel(FakeBedrock(error=ClientError("ValidationException")), "p", "m")
        with self.assertRaises(ClientError):
            model.complete("s", "p")

    def test_truncated_reply_is_an_output_error(self):
        model = BedrockModel(FakeBedrock(reply('{"claims": [', "max_tokens")), "p", "m")
        with self.assertRaises(ModelOutputError):
            model.complete("s", "p")


class ReplyParsingTests(unittest.TestCase):
    def test_json_inside_a_code_fence(self):
        self.assertEqual(parse_json_reply('```json\n{"topic": "health"}\n```'), {"topic": "health"})
        with self.assertRaises(ModelOutputError):
            parse_json_reply("No JSON here")

    def test_summary_fields_are_coerced(self):
        topic, claims = parse_summary('{"topic": "weather", "claims": [{"type": "rumour", '
                                      '"speakers": "Ms Rina Lim", "text": " x ", "paragraph": "¶2"}]}')
        self.assertEqual(topic, "other")
        self.assertEqual(claims, [{"type": "statement", "speakers": ["Ms Rina Lim"], "text": "x",
                                   "paragraph": 2, "quote": ""}])
        with self.assertRaises(ModelOutputError):
            parse_summary('{"claims": "none"}')

    def test_prompt_numbers_paragraphs_and_summary_cites_them(self):
        document = fakes.sitting()
        prompt = build_prompt(document, document["segments"][0])
        self.assertIn(f"Segment ID: {fakes.SEGMENT_ID}", prompt)
        self.assertIn("[¶4] Dr Aaron Koh: We will publish", prompt)
        text = render_summary("seg", [{"type": "answer", "text": "A.", "paragraph": 2},
                                      {"type": "question", "text": "Q?", "paragraph": 1}])
        self.assertEqual(text, "Question: Q? [seg ¶1]\nAnswer: A. [seg ¶2]")


if __name__ == "__main__":
    unittest.main()
