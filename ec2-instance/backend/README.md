# Backend — Parliament in Five

Express 5 + TypeScript + AWS SDK v3. Serves the React build, reads DynamoDB report
metadata, and retrieves private S3 JSON. No database writes or model calls.

## Data contract

The DynamoDB table has string partition key `HansardReportSummaryId`, no sort key:

```json
{
  "HansardReportSummaryId": "report-2026-10-20",
  "DateOfRelease": "2026-10-20",
  "ActualReportLink": "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=6-10-2026",
  "S3BucketLink": "s3://your-summary-bucket/summaries/report-2026-10-20.json"
}
```

The date above is illustrative, not a claim about the linked report's actual
publication date. Dates must be real ISO calendar dates. The publisher must
provide true release dates rather than reuse the ingestion pipeline's sitting dates.
Only approved public reports belong in this table.

The referenced S3 object has exactly two nonempty string fields:

```json
{
  "title": "Parliament in Five: report highlights",
  "body": "Opening summary paragraph.\n\nA second paragraph covering another discussion."
}
```

No release date is stored in S3 or added to the detail response. The body is
plain text. Invalid JSON, extra fields, arrays, and missing/empty fields are
treated as invalid stored content and produce HTTP 500.

S3 locations may be `s3://bucket/key`, virtual-hosted regional HTTPS URLs, or
regional path-style HTTPS URLs. URLs must identify the configured bucket on
standard AWS S3 endpoints. Expiring signed URL credentials are unnecessary:
the backend extracts the location and uses its own AWS credentials. Arbitrary
HTTP hosts, credentials, ports, fragments, and non-S3 URLs are rejected.

## Endpoints

### `POST /api/summary`

Send no body or `{}`. Performs a projected DynamoDB scan, follows all
`LastEvaluatedKey` pages, validates metadata, and returns an array:

```json
[
  {
    "DateOfRelease": "2026-10-20",
    "ActualReportLink": "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=6-10-2026",
    "HansardReportSummaryId": "report-2026-10-20"
  }
]
```

Returns `[]` if the table is empty. Sorting/pagination happen in the frontend.

### `POST /api/detail`

Body: `{ "hansardSummaryId": "report-2026-10-20" }`.
Uses DynamoDB `GetItem`, retrieves `S3BucketLink`, downloads and parses the S3
object, validates its title/body contract, and returns that object unchanged.
The configured byte limit applies while streaming the S3 body.

### Errors and health

`400` invalid request, `404` unknown ID/API route, `500` AWS/internal/stored-data
failure. Body: `{ "error": { "code": "INTERNAL_ERROR", "message": "..." } }`.
Malformed/oversized request bodies are request errors. Errors never expose stack
traces or storage locations. Server logs include operational details, not bodies
or credentials. `GET /api/health` is a process-only liveness endpoint.

## Configuration

For a preview without AWS, run `npm run start:local` from the repository root.
It builds the frontend and starts this Express app with an in-memory repository
of 25 fictional reports. Both POST endpoints and production static routing remain
the same. This mode requires no AWS settings and always binds to `127.0.0.1`.
The backend-folder `npm run start:local` reuses the existing frontend build.
Mock data lives in `src/local-data.ts` and is never selected by the production
entry point. See the overall README for the complete local-preview commands.

Copy `.env.example` to `.env`, then supply real table/bucket names. Configuration
is validated before listening. Environment values already set by the process
take precedence over `.env`. File/build paths resolve from the backend folder,
not the invoking shell's current directory.

| Variable                    | Default            | Purpose                         |
| --------------------------- | ------------------ | ------------------------------- |
| `NODE_ENV`                  | `development`      | Runtime environment             |
| `HOST`                      | `127.0.0.1`        | Bind address                    |
| `PORT`                      | `3000`             | HTTP port                       |
| `AWS_REGION`                | `ap-southeast-1`   | DynamoDB/S3 region              |
| `DYNAMODB_TABLE_NAME`       | Required           | Approved report metadata table  |
| `S3_SUMMARY_BUCKET`         | Required           | Only allowed summary bucket     |
| `FRONTEND_DIST_PATH`        | `../frontend/dist` | Built frontend directory        |
| `AWS_CONNECTION_TIMEOUT_MS` | `3000`             | AWS connection timeout          |
| `AWS_REQUEST_TIMEOUT_MS`    | `10000`            | Per-attempt AWS request timeout |
| `AWS_MAX_ATTEMPTS`          | `2`                | Bounded SDK retry attempts      |
| `MAX_SUMMARY_BYTES`         | `1048576`          | Maximum downloaded summary size |
| `LOG_LEVEL`                 | `info`             | `info`, `error`, or `silent`    |

Use the standard AWS credential chain: local profile for development, EC2 role
in production. `AWS_PROFILE` may be set in your local shell. Never commit keys.
AWS service endpoints derive from the region; public bucket URLs are unnecessary.

```sh
npm ci
npm run dev
npm run check
npm run build
npm start
```

`check` runs TypeScript and ESLint. Production startup requires a frontend build;
development can serve APIs without one. Missing asset requests do not receive
SPA HTML. The SPA fallback handles only `/` and summary reader URLs; unknown
browser routes receive the frontend not-found page with HTTP 404.

SIGTERM/SIGINT initiate graceful HTTP shutdown. The overall README describes
running Express directly on EC2, IAM, and production configuration.

## Manual verification

Use curl or a REST client to exercise both POST endpoints, empty scans,
multi-page scans, invalid/missing IDs, inaccessible objects, invalid stored JSON,
and dependency failures. Confirm internal failures return 500 JSON and unknown
API routes never return SPA HTML. Build both projects and check direct summary
refresh through Express. No automated test cases are included.
