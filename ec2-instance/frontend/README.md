# Frontend — Parliament in Five

React + TypeScript + Vite + React Router. Express serves `dist/` in production;
the Vite server is used only during development. Assumes public reports, ISO
release dates from DynamoDB, and a plain-text title/body summary from S3.

## Routes and presentation

- `/`: introduction, report archive, loading/empty/error states, 20-row pagination.
- `/summary/:hansardSummaryId`: fetch and display only `title` and `body`, with
  Back home and retry controls. Supports direct navigation and refresh.
- Other routes: not-found page.

The interface uses an editorial cream/navy/red palette, responsive CSS, semantic
tables, visible keyboard focus, and reduced-motion support. Source links open a
new tab. The archive sorts newest first with ID as a tie-breaker. Row numbers
continue across pages. All user-visible labels/copy live in `src/constants.ts`.
Summary body content is escaped text; blank lines produce paragraphs.

## Configuration and commands

To preview the built frontend served by Express with mock data, run
`npm run start:local` from the repository root, then visit
`http://127.0.0.1:3000`. It builds this project and serves 25 fictional reports
through the real API routes. No AWS configuration or separate Vite server is needed.

Copy `.env.example` to `.env`; Vite reads configuration at startup/build time.
All `VITE_*` variables are public: never put AWS credentials or secrets here.

| Variable               | Default                 | Purpose                          |
| ---------------------- | ----------------------- | -------------------------------- |
| `VITE_API_BASE_URL`    | `/api`                  | API base URL, no endpoint suffix |
| `VITE_API_TIMEOUT_MS`  | `30000`                 | Browser request timeout          |
| `DEV_PORT`             | `5173`                  | Vite development port            |
| `DEV_API_PROXY_TARGET` | `http://127.0.0.1:3000` | Development `/api` proxy         |

```sh
npm ci
npm run dev
npm run check
npm run build
```

`check` runs TypeScript and ESLint. `build` type-checks and emits `dist/`. No
automated test cases are included. Production uses same-origin `/api`, so no
CORS setup is required. If using a different API origin, that service must
explicitly permit the frontend origin; this backend assumes same-origin access.

## API integration

On homepage entry: `POST /api/summary`, no body. The response is an array of
`{ DateOfRelease, ActualReportLink, HansardReportSummaryId }` objects.

On reader entry: `POST /api/detail`, JSON body `{ "hansardSummaryId": "id" }`.
The response contains only `{ "title": "...", "body": "..." }`.
The reader neither requires nor displays a release date from this endpoint.

A shared API client validates response shapes and handles non-2xx responses,
invalid JSON, network errors, and timeouts. Leaving a page cancels its request.
Errors offer retry; a successful empty archive has its own message.

## Manual acceptance

Check 0, 1, 20, and 21+ records; dates/order/continuous numbering; report links;
direct summary loads and refresh; multiline body; API failures and retry;
unknown routes; narrow screens; keyboard navigation; and the Express-served build.
See the overall README for EC2 setup and known scaling limits.
