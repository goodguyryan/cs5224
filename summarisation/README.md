# Parliament in Five: summaries and weekly digest

Turn the scraper's processed sittings into checked item summaries and one weekly
digest of 700 to 900 words. Everything waits in a review table until a reviewer
approves it; only then does the EC2 reader see it. The reader never calls a model.

```text
Step Functions
  -> list_items_handler        week -> segments in processed/sittings/
  -> Map: summarise_item_handler    one segment -> Bedrock -> citation check -> review table
  -> build_digest_handler      week's item claims -> Bedrock -> digest -> review table
reviewer
  -> scripts/approve_week.py   approve: S3 {title, body} + reader table row; reject: nothing published
```

## Read these files in order

1. `lambda_function.py`: the three Lambda entry points.
2. `src/digest/pipeline.py`: duplicates, revisions, and failure marking.
3. `src/digest/summarise.py`: the item prompt and its JSON reply.
4. `src/digest/citations.py`: quote and speaker checks.
5. `src/digest/compose.py`: the digest prompt, its checks, and the reader's plain text.
6. `src/digest/publish.py`: approval and rejection.

## Items, claims and citations

An item is one entry in a sitting's `segments`, identified by `local_segment_id`.
The prompt numbers the segment's paragraphs (`content_text` split on blank lines)
and asks for at most eight claims. Each claim has a type (question, answer, decision
or statement), the speakers as the text names them, a paragraph number and a quote.
A source location is `2026-10-06/takesSectionVOList/0014 ¶3`.

A claim is kept only if all of these hold:

- the cited paragraph exists;
- the quote has at least four words and appears in that paragraph, ignoring case,
  punctuation and spacing;
- every named speaker appears in the segment, either as written, without a leading
  title such as Mr or Dr, or as the name in brackets after an office;
- a question or answer names a speaker.

Other claims are kept in `flagged_claims` with their reasons. Set
`CITATION_MODEL_CHECK=true` to also ask the model whether each passing quote
supports its claim. The checks cannot tell which of two people named in a segment
said something; the evaluation's speaker score measures that.

The digest prompt sees only kept claims, by ID such as `3.2`. A digest paragraph
citing an unknown ID is dropped. A paragraph naming a speaker it does not cite is
kept but flagged for the reviewer. A draft outside 700 to 900 words is regenerated
once; if still outside, it is saved with `word_count_ok: false`. A thin week gives
a short digest rather than padding.

## Revisions and failures

| Situation | Result |
|---|---|
| Item unchanged (same SHA-256 of `content_text`) | Skipped; no model call |
| Item changed | New revision, status `pending` |
| Item or digest fails | Status `failed`, `last_error` set; the next run retries the same revision |
| Week's included items unchanged | Digest skipped |
| An included item changed | New digest revision, status `pending`; the published version stays until approved |
| Week has no items with claims | No digest record |

Failed items stay out of the digest and are listed in its `failed_items`.

## Review table

| Key | Value |
|---|---|
| Partition key `week_id` (String) | `2026-W41`, ISO week, Monday to Sunday by sitting date |
| Sort key `record_id` (String) | `DIGEST`, or `ITEM#<local_segment_id>` |

Both record types have `status` (`pending`, `approved`, `rejected`, `failed`),
`revision`, `sitting_dates`, `topic_tags`, `hansard_urls`, `s3_keys`,
`source_locations`, `model_id`, `created_at` and `updated_at`.

Items add `segment_id`, `content_hash`, `title`, `subtitle`, `raw_key`,
`source_sha256`, `summary`, `claims` and `flagged_claims`. Digests add `title`,
`body`, `sections`, `cited_items`, `sittings`, `word_count`, `word_count_ok`,
`dropped_paragraphs`, `speaker_flags`, `failed_items`, `item_revisions` and
`items_fingerprint`, and after review `reviewed_at`, `published_revision`,
`published_reader_id` and `published_s3_link`.

## Publishing

`scripts/approve_week.py 2026-W41` prints the digest and its checks, then asks to
approve, reject or quit. Approval writes `summaries/digest-2026-W41.json` containing
only `title` and `body` to `S3_SUMMARY_BUCKET`, then this row to the reader table:

```json
{
  "HansardReportSummaryId": "digest-2026-W41",
  "DateOfRelease": "2026-10-13",
  "ActualReportLink": "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=8-10-2026",
  "S3BucketLink": "s3://YOUR_SUMMARY_BUCKET/summaries/digest-2026-W41.json"
}
```

`DateOfRelease` is the approval date in Singapore. `ActualReportLink` is the week's
latest sitting; the body ends with a `Sources` list of every sitting it covers.
Approval also marks the digest's items `approved`. Rejection publishes nothing.

## Earlier-topic links

A digest section links to an approved digest from the previous eight weeks only when
an earlier cited item has the same topic and its heading either matches the current
item's heading or appears in the current item's original Hansard text.

## Local commands (PowerShell)

Python 3.11+. The tests and evaluation need no AWS access or third-party packages.
Run from the `summarisation/` directory:

```powershell
& ..\.venv\Scripts\python.exe -m unittest discover -s .\tests -v
& ..\.venv\Scripts\python.exe .\scripts\evaluate.py --replay
```

`--replay` answers from each gold week's `replay.json`. Without it, the script calls
Bedrock using the environment variables in `.env.example`. A gold week folder holds
`processed/sittings/*.json` in the scraper's format and `reference.json` with key
points: a key point is covered when one digest paragraph contains all its keywords,
and its speaker is checked against the claims that contain them. The example week
`gold/2026-W41` is fictional and has deliberate mistakes in `replay.json`.

No AWS resources are created by this project. For deployment, place
`lambda_function.py` and `src/` at the ZIP root.
