import unittest

import fakes  # noqa: F401
from digest.citations import check_claims, claim_problems, speaker_in_text

PARAGRAPHS = [
    "Ms Rina Lim asked the Minister for Health about clinic waiting times.",
    "The Minister for Health (Dr Aaron Koh): The median wait fell from “forty days” to thirty-two days.",
]
TEXT = "\n\n".join(PARAGRAPHS)


def claim(**overrides):
    value = {"type": "answer", "speakers": ["Dr Aaron Koh"], "text": "The wait fell.",
             "paragraph": 2, "quote": 'The median wait fell from "forty days"'}
    value.update(overrides)
    return value


class ClaimCheckTests(unittest.TestCase):
    def test_quote_matches_despite_punctuation_and_case(self):
        self.assertEqual(claim_problems(claim(quote="the MEDIAN wait fell from forty days"), PARAGRAPHS, TEXT), [])

    def test_quote_must_be_in_the_cited_paragraph(self):
        problems = claim_problems(claim(paragraph=1), PARAGRAPHS, TEXT)
        self.assertEqual(problems, ["quote not found in cited paragraph"])

    def test_missing_paragraph_and_short_quote(self):
        self.assertIn("cited paragraph does not exist", claim_problems(claim(paragraph=9), PARAGRAPHS, TEXT))
        self.assertIn("cited paragraph does not exist", claim_problems(claim(paragraph=None), PARAGRAPHS, TEXT))
        self.assertIn("quote is too short to support the claim",
                      claim_problems(claim(quote="forty days"), PARAGRAPHS, TEXT))

    def test_named_speaker_must_appear_in_segment(self):
        problems = claim_problems(claim(speakers=["Mr Daniel Ong"]), PARAGRAPHS, TEXT)
        self.assertEqual(problems, ["speaker not in cited segment: Mr Daniel Ong"])

    def test_question_and_answer_need_a_speaker(self):
        self.assertEqual(claim_problems(claim(speakers=[]), PARAGRAPHS, TEXT), ["answer has no speaker"])
        self.assertEqual(claim_problems(claim(type="decision", speakers=[]), PARAGRAPHS, TEXT), [])

    def test_speaker_forms(self):
        self.assertTrue(speaker_in_text("The Minister for Health (Dr Aaron Koh)", TEXT))
        self.assertTrue(speaker_in_text("Aaron Koh", TEXT))
        self.assertTrue(speaker_in_text("Mdm Rina Lim", TEXT))
        self.assertFalse(speaker_in_text("Mr Tan (Example GRC)", "Ms Lee (Example GRC) asked"))
        self.assertFalse(speaker_in_text("Mr Koh", "Mr Kohli asked"))

    def test_split_into_supported_and_flagged(self):
        supported, flagged = check_claims([claim(), claim(paragraph=1)], PARAGRAPHS, TEXT)
        self.assertEqual(len(supported), 1)
        self.assertEqual(flagged[0]["problems"], ["quote not found in cited paragraph"])

    def test_optional_model_check_runs_only_on_passing_claims(self):
        model = fakes.FakeModel('{"supported": false}')
        supported, flagged = check_claims([claim(), claim(paragraph=1)], PARAGRAPHS, TEXT, model)
        self.assertEqual(supported, [])
        self.assertEqual(flagged[0]["problems"], ["model check: passage does not support the claim"])
        self.assertEqual(len(model.calls), 1)
        self.assertIn(PARAGRAPHS[1], model.calls[0])


if __name__ == "__main__":
    unittest.main()
