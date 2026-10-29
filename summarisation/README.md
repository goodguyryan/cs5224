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

No AWS resources are created by this project.

## AWS deployment (code prepared, not deployed)

Use `ap-southeast-1` throughout. The scraper's buckets and the reader's table and
summary bucket are set up by their own guides; these steps cover this folder only.

1. **Bedrock model access.** Enable Amazon Nova Lite. Under cross-region inference,
   confirm the APAC profile ID matches `BEDROCK_INFERENCE_PROFILE`
   (`apac.amazon.nova-lite-v1:0`).
2. **Review table.** Create a DynamoDB table with on-demand capacity, String
   partition key `week_id` and String sort key `record_id`, and no indexes. It is
   separate from the reader's table, which holds only approved reports.
3. **Lambda execution role.** Trust `lambda.amazonaws.com`, attach
   `AWSLambdaBasicExecutionRole`, and add:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "ReadProcessedSittings",
         "Effect": "Allow",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::YOUR-PROCESSED-BUCKET/processed/sittings/*"
       },
       {
         "Sid": "RecognizeMissingSittings",
         "Effect": "Allow",
         "Action": "s3:ListBucket",
         "Resource": "arn:aws:s3:::YOUR-PROCESSED-BUCKET"
       },
       {
         "Sid": "ReviewRecords",
         "Effect": "Allow",
         "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"],
         "Resource": "arn:aws:dynamodb:ap-southeast-1:ACCOUNT_ID:table/YOUR-REVIEW-TABLE"
       },
       {
         "Sid": "InvokeNovaLiteThroughApacProfile",
         "Effect": "Allow",
         "Action": "bedrock:InvokeModel",
         "Resource": [
           "arn:aws:bedrock:ap-southeast-1:ACCOUNT_ID:inference-profile/apac.amazon.nova-lite-v1:0",
           "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0"
         ]
       }
     ]
   }
   ```

   The profile routes requests to other APAC Regions, so the model ARN needs every
   Region the profile lists; `*` covers them.
4. **Package.** Build a ZIP whose root contains `lambda_function.py` and `src/`
   (`src/digest/*.py`), as in the scraper's packaging guide. Do not include `tests/`,
   `gold/`, `scripts/` or `.env`.
5. **Three functions from the one ZIP.** Python 3.13, the role from step 3:

   | Function | Handler | Timeout | Memory |
   |---|---|---|---|
   | list items | `lambda_function.list_items_handler` | 60 s | 512 MB |
   | summarise item | `lambda_function.summarise_item_handler` | 120 s | 512 MB |
   | build digest | `lambda_function.build_digest_handler` | 900 s | 512 MB |

   Set `PROCESSED_BUCKET`, `REVIEW_TABLE`, `BEDROCK_MODEL_ID`,
   `BEDROCK_INFERENCE_PROFILE` and optionally `CITATION_MODEL_CHECK` on each.
   Lambda sets `AWS_REGION` itself.
6. **State machine.** After the scraper's task:

   ```text
   ListItems     input {}  (or {"week": "2026-W41"} for a manual run)
   Map           ItemsPath $.items, MaxConcurrency 4, ResultPath null
     SummariseItem
       Retry RetryableError: IntervalSeconds 5, BackoffRate 2, MaxAttempts 4
       Retry ModelOutputError: MaxAttempts 1
       Catch States.ALL -> next item (the item is already marked failed)
   BuildDigest   input {"week.$": "$.week"}
       Retry RetryableError: IntervalSeconds 10, BackoffRate 2, MaxAttempts 3
   ```

   Do not retry `ItemError`, `ValueError` or `KeyError`. The Step Functions role
   needs `lambda:InvokeFunction` on the three functions and the scraper.
7. **Schedule.** Point EventBridge Scheduler at the state machine rather than the
   scraper Lambda, for example `cron(0 9 ? * MON *)` in `Asia/Singapore` with input
   `{}`. The scheduler role needs `states:StartExecution`. Scheduled runs digest
   the previous week; run a later sitting's week again by hand.
8. **Reviewer access.** Whoever runs `scripts/approve_week.py` needs their own
   credentials with `dynamodb:GetItem`, `Query` and `PutItem` on the review table,
   `dynamodb:PutItem` on the reader table, and `s3:PutObject` on
   `arn:aws:s3:::YOUR_SUMMARY_BUCKET/summaries/*`. Set `AWS_REGION`,
   `REVIEW_TABLE`, `DYNAMODB_TABLE_NAME` and `S3_SUMMARY_BUCKET` in that shell.
   The EC2 reader role stays read-only.
9. **First run.** Start the state machine by hand with a week that has sittings.
   Check the review table for `ITEM#...` records and a `pending` `DIGEST`, then run
   `approve_week.py` for that week and confirm the digest appears on the reader site.
   Add a CloudWatch alarm on failed executions.
