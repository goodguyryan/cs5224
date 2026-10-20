# Parliament in Five: Hansard retrieval

Download full Singapore Parliament sittings from SPRS and produce JSON for later
summarisation. Local runs and the future Lambda entry point use the same workflow.

Detailed guides:

- [Lambda deployment and EventBridge Scheduler setup](README_LAMBDA_EVENTBRIDGE.md)
- [Output structure and downstream Bedrock processing](README_OUTPUT_BEDROCK.md)

The current summarisation input is the main Hansard transcript in English.
Original-language speech PDFs are outside that input; see
[the vernacular PDF decision](#vernacular-pdfs-raw-metadata-only).

## Read these files in order

1. `scripts/retrieve_window.py`: local command-line entry point.
2. `src/hansard/pipeline.py`: `run_window()` decides what to fetch or skip.
3. `src/hansard/client.py`: SPRS requests, cookies, timeouts, retries, and pacing.
4. `src/hansard/parser.py`: validates and preprocesses the downloaded JSON.
5. `src/hansard/storage.py`: the same `exists`, `read`, and `write` operations for
   local files and S3.
6. `lambda_function.py`: future `lambda_function.lambda_handler` entry point.

## The complete workflow

The retrieval function accepts exactly two dates: `from_date` and `to_date`.
Both endpoints are included. To process one sitting date, use the same date for both.
For every date in that range:

```text
processed file exists? -> skip
otherwise raw exists?  -> preprocess saved raw, then save processed
otherwise             -> searchResult checks whether a sitting exists
                         getHansardReport retrieves it if present
                         validate date, save raw, preprocess, save processed
```

The processed file is the completion marker. If a run stops after saving raw JSON,
the next run resumes without downloading again. If preprocessing is complete, the
next run skips it too. A processed file is always skipped; there is no override or
reprocessing flag. Nothing compares past versions or refreshes dates already downloaded.

`searchResult` can report an empty search as either an empty JSON list or HTTP 500
with the exact JSON marker `{"errorCode":0,"description":"No Results Found"}`.
Both mean `not_found` and do not trigger retries or a report download. This exception
applies only to that specific response from `searchResult`. Other HTTP errors,
malformed responses, and all full-report HTTP 500s retain normal failure handling.
Neither pagination nor `maxResult` is needed.

The client POSTs directly to `searchResult` and `getHansardReport`. There is no
preliminary GET to the portal and no separate website health check. The portal's
HTML page can return HTTP 404 while the JSON endpoints work. API errors are handled
by the existing retries and validation. Cookies returned by the APIs can still be
retained automatically; no browser visit is needed to establish them first.

The range uses sitting dates, not publication dates. Non-sitting dates are not cached,
so a newly published sitting within a later run's range can still be discovered.

## Two files per sitting

```text
data/
  raw/sittings/2026-10-06.json
  processed/sittings/2026-10-06.json
```

The raw file preserves the exact response bytes. The processed file contains sitting
metadata, source URL, collection counts, warnings, supporting records, and an array
of transcript segments. Source records, including original HTML, are retained in
each segment under `source_record`. Text conversion keeps paragraph boundaries,
speaker text, clarification text, and footnotes; it does not identify speaker turns.

## Parser output, without reading its implementation

`parse_sitting()` returns one Python dictionary for one sitting. The pipeline saves
that dictionary as `processed/sittings/YYYY-MM-DD.json`. It is not a separate file
per segment. This abbreviated example shows one of 152 segments; the full output
has all segments, original metadata, and supporting records:

```json
{
  "sitting_id": "2026-10-06",
  "sitting_date": "2026-10-06",
  "source": {
    "public_url": "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=6-10-2026",
    "raw_key": "raw/sittings/2026-10-06.json",
    "sha256": "<64 hexadecimal characters>"
  },
  "metadata": {"sittingDate": "06-10-2026", "volumeNO": 96},
  "collection_counts": {"takesSectionVOList": 152, "a2bList": 4},
  "supporting_collections": {"a2bList": [{"bill": "Original supporting text"}]},
  "segment_count": 152,
  "segments": [
    {
      "local_segment_id": "2026-10-06/takesSectionVOList/0014",
      "source_position": {"collection": "takesSectionVOList", "index": 14},
      "title": "Digital Infrastructure Bill",
      "subtitle": null,
      "section_type": "BP",
      "report_type": null,
      "question_number": null,
      "content_text": "Order for Second Reading read.\n\nFurther transcript text...",
      "source_record": {"content": "<p>Original HTML...</p>"}
    }
  ],
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `sitting_id`, `sitting_date` | ISO sitting date, used as the sitting identity |
| `source` | Human-facing link, saved raw object's key, and raw-response checksum |
| `metadata` | Original SPRS sitting metadata, without renaming its fields |
| `collection_counts` | Source record counts, including vernacular PDF references; these are not all transcript counts |
| `supporting_collections` | Attendance, ATBP, annexure references, and other non-transcript lists, excluding `vernacularList` |
| `segment_count` | Number of emitted transcript segments |
| `segments` | Ordered transcript records ready for downstream processing |
| `warnings` | Extraction limitations such as an unknown collection or missing text |

Each segment has a readable local ID, original collection/index, title and category
fields, cleaned `content_text`, and its complete original `source_record` including
HTML and footnotes. Nullable source fields remain `null`. For summarisation, use
each segment's `title` and `content_text`; `source_record` is the source reference.

### Why the parser accepts raw bytes

The parser immediately decodes the bytes into a Python dictionary (`payload`) and
then extracts fields from that dictionary. It does not process byte values as text.
Accepting bytes gives downloaded and cached data exactly the same processing path:

```text
HTTP response bytes or saved local/S3 bytes
  -> JSON decode -> payload dictionary -> extracted segments -> processed dictionary
```

It also lets `source.sha256` identify the exact saved raw object. Reserializing a
payload dictionary may change whitespace, key ordering, or encoding, so its bytes
need not match the original HTTP response. A payload-based parser is possible, but
would still need the original bytes separately to calculate this exact checksum.

There is one SHA-256 field: `source.sha256`, calculated over the saved raw bytes.
It is a source fingerprint. Whitespace changes in raw JSON also change it. It is
not used as the sitting ID or to decide whether a date is complete.

IDs are readable:

```text
sitting_id:       2026-10-06
local_segment_id: 2026-10-06/takesSectionVOList/0014
```

The segment ID is a local locator based on date, collection, and zero-based index.
Repeated titles are valid and remain separate. IDs may shift if the source is
reordered; tracking such changes is outside the current scope.

## Collection coverage and validation

`takesSectionVOList` must exist as a list because it identifies the full-report
structure we currently understand. Missing main content is an error, rather than
silently recording the date as complete with an empty report.

The saved 6 October sitting has 152 transcript records in `takesSectionVOList`.
`writtenAnswersVOList` and `writtenAnsNAVOList` are also recognized as potential
transcript collections, but are empty in this fixture, so their non-empty schemas
remain unverified.

This is not a definitive SPRS schema. Unknown top-level lists produce warnings and
are retained under `supporting_collections`. Unextractable transcript text also
produces a warning and keeps its source record. Supporting data such as attendance,
ATBP, and annexure references is retained but is not treated as transcript text.
Annexure files themselves are not downloaded. The raw response preserves all fields.

### Vernacular PDFs: raw metadata only

`vernacularList` is a catalogue of separate original-language speech PDFs. A record
has fields such as `vernacularID`, `vernacularTitle`, `fileName`, and `filePath`.
It describes a document and does not contain inline transcript text to clean.
The `d:/apps/...` paths in these records belong to Parliament's server; they are
not local project paths or directly usable public download URLs.

In the saved 9 and 10 September sittings, all 16 PDF filenames also appear in links
inside the main transcript. Sampled speeches marked "In Mandarin" or "In Malay"
have English speech text following those links. For the current English summary,
we use that main transcript and exclude the PDF versions from the input. Comparing
translations or preserving original-language wording for analysis is outside scope.

The processing decisions are:

- Do not download the vernacular PDFs or attempt PDF text extraction.
- Do not create transcript segments from their reference records.
- Exclude them from `segment_count` and `supporting_collections`.
- Keep the original reference records in the unmodified raw JSON only.
- Keep their source count in `collection_counts.vernacularList` for visibility.
- Do not emit missing-text warnings for these known PDF reference records.

For downstream summarisation, use `segments[].title` and `segments[].content_text`.
Do not add the PDF references or their counts as extra speeches. This avoids empty
segments and the possibility of giving one speech extra weight through multiple
language versions.

| Sitting | Transcript segments | PDF references retained in raw JSON | Expected vernacular missing-text warnings |
|---|---:|---:|---:|
| 9 September 2026 | 168 | 12 | 0 |
| 10 September 2026 | 147 | 4 | 0 |

The previous totals of 180 and 151 included empty PDF-reference segments. Those two
local processed outputs were corrected once as part of the bug fix, using saved raw
data. Normal runs continue to skip every date whose processed file already exists;
no general reprocessing option has been added.

## Local commands (PowerShell)

Python 3.11+ is sufficient. There are no third-party requirements for local use.
Run commands from the `webscraping/` directory with the existing virtual environment
at the repository root:

```powershell
cd .\webscraping
```

Inspect the saved sitting without writes or HTTP requests:

```powershell
& ..\.venv\Scripts\python.exe .\scripts\inspect_sitting.py
```

Retrieve one sitting date (skip if already complete; recover automatically if raw exists):

```powershell
& ..\.venv\Scripts\python.exe .\scripts\retrieve_window.py --from-date 2026-10-06 --to-date 2026-10-06
```

Discover and download missing sittings within an explicit range:

```powershell
& ..\.venv\Scripts\python.exe .\scripts\retrieve_window.py --from-date 2026-09-21 --to-date 2026-10-20
```

Both date arguments are required. The earlier `--date`, `--lookback`, `--reprocess`,
and `--offline` options have been removed. Local and Lambda runs follow the same
three rules: skip processed, recover raw-only, otherwise discover and download.
Use `inspect_sitting.py` to inspect saved data without network requests or writes.

The core function call is:

```python
run_window(store, client, from_date=date(2026, 9, 21), to_date=date(2026, 10, 20))
```

`--delay` is the minimum pause between HTTP requests,
including retries. The default is one second. `--retries` means
maximum attempts, default two. Per-request timeout is 20 seconds. HTTP 5xx (except
the recognized empty-search response), 429, and connection failures are retried;
exhausted failures are reported and not cached
as non-sitting dates. The CLI exits with code 1 if any date fails.

Run the offline workflow checks:

```powershell
& ..\.venv\Scripts\python.exe -m unittest discover -s .\tests -v
```

## EventBridge -> Lambda -> S3 (code prepared, not deployed)

```text
EventBridge schedule
  -> lambda_function.lambda_handler(event, context)
    -> run_window(S3HansardStore(...), HansardClient())
      -> raw bucket:       raw/sittings/YYYY-MM-DD.json
      -> processed bucket: processed/sittings/YYYY-MM-DD.json
```

Set `RAW_BUCKET` and `PROCESSED_BUCKET` as Lambda environment variables; they can
refer to one bucket or two. The handler imports Boto3 only when invoked. AWS Python
runtimes include Boto3; pin/package its dependencies when preparing deployment.

The local entry point already selects `LocalHansardStore`; `lambda_function.py`
already selects `S3HansardStore`. You do not edit the local script to deploy Lambda.

### Environment template

`.env.example` lists the only two application environment variables:

```dotenv
RAW_BUCKET=replace-with-your-raw-bucket-name
PROCESSED_BUCKET=replace-with-your-processed-bucket-name
```

You can copy it to `.env` as a personal configuration reference:

```powershell
Copy-Item .\.env.example .\.env
```

Lambda and this project do not automatically load `.env` files. During deployment,
set these two values in Lambda's Configuration > Environment variables, or configure
the same variables in your deployment tool. The handler reads `os.environ`.
The local retrieval script uses `--data-root` rather than these settings.

Use bucket names only; no `s3://` prefix or HTTPS URL. Credentials come from the
execution role. `.env` and personal `.env.*` files are ignored by Git; the example
template remains eligible for version control. No dotenv dependency is required.

For a manual Lambda invocation, supply both dates:

```json
{"from_date": "2026-09-21", "to_date": "2026-10-20"}
```

For a scheduled invocation, use `{}`. Only the Lambda wrapper computes the fixed
30-calendar-day range ending today in Singapore; it passes the two resulting dates
to `run_window`. This retains the agreed weekly discovery window without adding
competing date controls to the core function. Supplying only one date is an error.
The `lookback` event field has been removed. The fixed default is scheduling policy,
not an argument to preprocessing or retrieval.

For deployment, place `lambda_function.py` and the `src/` directory at the ZIP root;
configure the handler as `lambda_function.lambda_handler`.

### Storage and identity on AWS

For someone familiar with Google Cloud, the approximate service roles are:

| Google Cloud concept | AWS service in this design |
|---|---|
| Cloud Scheduler | EventBridge Scheduler |
| Cloud Functions / Cloud Run function | Lambda |
| Cloud Storage bucket | S3 bucket |
| Attached service account | Lambda execution role (IAM) |

The datastore is a small Python adapter, not a separate database server. Locally,
`LocalHansardStore` reads and writes files. On Lambda, `S3HansardStore` uses Boto3
to call S3. Lambda's temporary disk is not used as persistent state.

An S3 object's address consists of a bucket name and a key. For example:

```text
bucket: parliament-raw
key:    raw/sittings/2026-10-06.json
URI:    s3://parliament-raw/raw/sittings/2026-10-06.json
```

The SDK takes `Bucket` and `Key` arguments; no public or presigned URL is required.
`head_object` checks existence, `get_object` reads, and `put_object` writes. The
`RAW_BUCKET` and `PROCESSED_BUCKET` environment variables contain bucket names,
not URLs or credentials. The execution role authorizes access and provides temporary
credentials automatically; no access keys are stored in the code.

At deployment, the infrastructure consists of a schedule allowed to invoke the
Lambda function, the function and its execution role, and one or two S3 buckets.
The handler downloads SPRS data into memory and writes it directly to S3; later
invocations check the processed object in S3 to decide whether the date is complete.

The execution role will need S3 GetObject and PutObject permissions for both key
prefixes and ListBucket permissions scoped to those prefixes. Missing objects can
otherwise be reported as 403; the adapter treats 403 as an error, not a cache miss.
It closes downloaded S3 response streams and does not create buckets.

Retries skip complete processed files and recover raw-only dates. The handler raises
an exception if any date fails, so failures can participate in Lambda's retry/error
handling. Configure invocation retries and a failure destination at deployment.
Use one concurrent scheduled execution; no distributed locking is implemented.

Configure and measure Lambda timeout before deployment (AWS permits up to 900
seconds). Network delays and retries can exceed the budget for a 30-day run; completed
dates remain saved and a retry resumes. A long-running backfill may need smaller
windows. No AWS resources or schedules have been created by this project.

Reference: [scheduled Lambda invocation](https://docs.aws.amazon.com/lambda/latest/dg/with-eventbridge-scheduler.html),
[Python packaging](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html),
[S3 existence checks](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/head_object.html),
[Lambda execution roles](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html),
[Lambda temporary storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-ephemeral-storage.html),
[Lambda environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html).

## Previous generated layout

The current output uses one processed JSON file per date. Any existing
`processed/sittings/YYYY-MM-DD/manifest.json` and segment directory are earlier
generated output; they are left untouched and are not used for completion checks.
The original raw file generates the new output on a normal run when that processed
file is missing. Existing processed files are always skipped.
