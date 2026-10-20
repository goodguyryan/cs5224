# Deploying Hansard retrieval to Lambda and EventBridge Scheduler

This guide deploys the existing retrieval code. 


## 1. Understand what runs where

```text
EventBridge Scheduler -- event {} --> lambda_function.lambda_handler
                                       |
                                       v
                               run_window(S3HansardStore, HansardClient)
                                       |
                       SPRS discovery and full-report POST requests
                                       |
                          raw S3 object -> processed S3 object
```

`scripts/retrieve_window.py` is the local entry point and uses `LocalHansardStore`.
`lambda_function.py` is the AWS entry point and already uses `S3HansardStore`.

Both entry points use the same date-range workflow:

| State for a sitting date | Action |
|---|---|
| Processed object exists | Skip the date |
| Only raw object exists | Recover by processing the saved response |
| Neither object exists | Discover, download if present, then process |

## 2. Choose names and create the S3 buckets

The examples use these placeholders; replace them with your own names:

| Setting | Example |
|---|---|
| Region | `ap-southeast-1` (Singapore) |
| Lambda function | `parliament-hansard-retrieval` |
| Raw bucket | `YOUR-RAW-BUCKET` |
| Processed bucket | `YOUR-PROCESSED-BUCKET` |

Create the buckets in S3, normally in the same Region as Lambda. Leave public access
blocked. The SDK authenticates using the function's execution role; public links
are unnecessary. You may use one bucket for both environment variables.

The code uses these full object keys, even when the buckets are separate:

```text
s3://YOUR-RAW-BUCKET/raw/sittings/2026-10-06.json
s3://YOUR-PROCESSED-BUCKET/processed/sittings/2026-10-06.json
```

The bucket name and object key are separate arguments to Boto3. Lambda's local
temporary disk is not the persistent cache; S3 object existence is the saved state.

## 3. Create the Lambda execution role

Create an IAM role trusted by the Lambda service (`lambda.amazonaws.com`). Attach
`AWSLambdaBasicExecutionRole` for CloudWatch logging and add an S3 policy such as
the following, replacing both bucket placeholders:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadAndWriteSittingObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::YOUR-RAW-BUCKET/raw/sittings/*",
        "arn:aws:s3:::YOUR-PROCESSED-BUCKET/processed/sittings/*"
      ]
    },
    {
      "Sid": "RecognizeMissingObjects",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": [
        "arn:aws:s3:::YOUR-RAW-BUCKET",
        "arn:aws:s3:::YOUR-PROCESSED-BUCKET"
      ]
    }
  ]
}
```

`head_object` uses object-read permission. S3 can return 403 for an absent object
when the caller lacks `ListBucket`; the code intentionally does not treat 403 as
absence. List access here is limited to the two project buckets. Customer-managed
KMS encryption may also require permissions on your chosen key.
[S3 HeadObject permissions](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/head_object.html)

AWS automatically supplies the execution role's credentials to Lambda. Do not put
access keys in the code or `.env` template.
[Lambda execution roles](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html)

## 4. Build the deployment ZIP from PowerShell

Run this from the `webscraping/` directory containing `lambda_function.py` and `src/`:

```powershell
$packageId = [guid]::NewGuid().ToString('N')
$packageDir = Join-Path $env:TEMP ('hansard-lambda-' + $packageId)
$moduleDir = Join-Path $packageDir 'src\hansard'
New-Item -ItemType Directory -Path $moduleDir -Force | Out-Null
Copy-Item -LiteralPath .\lambda_function.py -Destination $packageDir
Get-ChildItem -LiteralPath .\src\hansard -Filter '*.py' -File |
    Copy-Item -Destination $moduleDir
$zipPath = Join-Path $env:TEMP ('hansard-lambda-' + $packageId + '.zip')
Compress-Archive -Path (Join-Path $packageDir '*') -DestinationPath $zipPath
Write-Output $zipPath
```

This creates a new package without changing the source or deleting local data.
Its root must contain:

```text
lambda_function.py
src/
  hansard/
    __init__.py
    client.py
    models.py
    parser.py
    pipeline.py
    storage.py
```

Do not wrap those files in an additional project directory. Do not upload `.venv`,
local data, tests, `.env`, or `__pycache__`. The handler adds `src/` to its import path.

The code uses the standard library and Boto3. The minimal package above relies on
the Boto3 included in the managed Python runtime. For a reproducible deployment,
AWS recommends packaging your tested SDK and all its dependencies; those packages
belong at the ZIP root alongside `lambda_function.py`. Do not copy a whole Windows
virtual environment to Lambda.
[Python ZIP packaging](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)

## 5. Create and configure the Lambda function

In the Lambda console, create a Python function in your chosen Region, select the
execution role from step 3, and upload the ZIP. Python 3.13 is an example compatible
with this project's Python 3.11+ syntax. Set the handler to:

```text
lambda_function.lambda_handler
```

Under **Configuration > Environment variables**, set:

```dotenv
RAW_BUCKET=YOUR-RAW-BUCKET
PROCESSED_BUCKET=YOUR-PROCESSED-BUCKET
```

These values are bucket names only. `.env.example` is a reference template;
Lambda and this project do not automatically read `.env` files.
[Lambda environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html)

For an initial small-project deployment, 512 MB memory and a 900-second timeout are
reasonable starting settings to measure, rather than a performance guarantee.
Set reserved concurrency to 1 to avoid overlapping retrieval invocations. The code
has no distributed lock. AWS permits a maximum Lambda timeout of 900 seconds;
slow requests or retries can still exhaust that budget. Use smaller explicit ranges
for long backfills.
[Lambda timeout](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html)

The function needs outbound HTTPS access to SPRS. For this public-data task, default
Lambda networking avoids unnecessary VPC setup. Attaching Lambda to a VPC changes
internet routing requirements; placing it in a public subnet alone does not provide
internet access.
[VPC internet access](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html)

## 6. Test a single sitting before scheduling

In the Lambda **Test** tab, create this JSON event:

```json
{
  "from_date": "2026-10-06",
  "to_date": "2026-10-06"
}
```

The date fields are at the top level, use ISO format, and are both inclusive. Do not
put them under `body` or `detail`. Supplying only one date is an error. The removed
`lookback` field is rejected. AWS supplies the handler's `context` argument itself.

Clicking Test runs real SPRS requests and S3 operations. Expect `downloaded` or
`recovered` in `processed`, or the date under `skipped` if already complete. A fresh
6 October response is expected to have 152 transcript segments. Confirm both S3
objects and inspect the function's CloudWatch logs. A second test should skip the
completed date without downloading or parsing again.

## 7. Create the recurring EventBridge Scheduler schedule

Use **EventBridge Scheduler**, then **Create schedule**. Choose a recurring schedule.
For example, Monday at 09:00 Singapore time is:

```text
Schedule expression: cron(0 9 ? * MON *)
Time zone:           Asia/Singapore
Flexible time window: Off
```

This is an example schedule, not an application requirement. Scheduler supports
named time zones for cron expressions.
[Scheduler schedule types](https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html)

Choose the **Lambda Invoke** target and select your function. Set the target input
JSON to:

```json
{}
```

The current handler turns `{}` into the fixed 30-calendar-day range ending on the
invocation's current Singapore date. For a run on 20 October 2026, that is
21 September through 20 October. It then passes those two dates to `run_window`.
It uses the execution date, not a scheduled timestamp from the event; a retry
crossing midnight can therefore use a slightly different range.

Do not hardcode dates in the recurring input unless you want to scan that same
fixed range every time. Explicit date events are useful for manual backfills.

Allow the console to create a Scheduler execution role, or select an existing role
trusted by `scheduler.amazonaws.com` and allowed to call `lambda:InvokeFunction` on
your exact Lambda ARN. This is separate from the function's S3 execution role:

| Role | Permission it supplies |
|---|---|
| Scheduler execution role | Invoke this Lambda function |
| Lambda execution role | Read/write project S3 objects and write logs |

Enable the schedule after the one-date test succeeds. Scheduler invokes Lambda
asynchronously; its target input becomes `event`.
[Scheduled Lambda invocation](https://docs.aws.amazon.com/lambda/latest/dg/with-eventbridge-scheduler.html)

## 8. Understand failure handling and monitoring

There are two different failure stages:

- Scheduler delivery: could Scheduler submit the invocation to Lambda? Configure
  its retry policy and, if wanted, its SQS dead-letter queue for delivery failures.
- Function execution: did the submitted Lambda run succeed? The handler prints the
  summary and raises if `failures` is non-empty. Configure Lambda asynchronous
  retries and an on-failure destination for these execution failures. A Scheduler
  delivery DLQ does not replace that function-execution failure destination.

Completed dates remain in S3 when a later date fails. Retries skip those completed
objects and recover raw-only objects. This supports repeated invocations but does
not promise exactly-once delivery or transactional writes across both buckets.
[Lambda asynchronous error handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)

Inspect CloudWatch errors and the logged `processed`, `skipped`, `not_found`, and
`failures` arrays. `not_found` is a normal outcome for a date without indexed results;
it should not fail the invocation. `warnings` concern extraction quality and need
review even when the invocation itself succeeds.

| Symptom | First thing to inspect |
|---|---|
| Cannot import `lambda_function` or `hansard` | ZIP root layout and handler name |
| Missing `RAW_BUCKET` / `PROCESSED_BUCKET` | Lambda environment configuration |
| S3 AccessDenied / 403 | Function execution role, bucket policy, and encryption settings |
| Timeout reaching SPRS | Internet routing and request/overall time budgets |
| Scheduler cannot invoke function | Scheduler role and selected target ARN |
| Lambda errors despite successful delivery | CloudWatch logs and Lambda failure destination |
| Existing date shows `skipped` | Expected completed-file behavior |

The 30-day range is a discovery policy, not the weekly summary's content window.
Data is discovered by sitting date, so reports published after that window require
a wider explicit range. Corrections to already completed sittings are outside the
current ingestion scope.
