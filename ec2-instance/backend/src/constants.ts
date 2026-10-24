export const ATTRIBUTES = {
  releaseDate: "DateOfRelease",
  reportLink: "ActualReportLink",
  summaryId: "HansardReportSummaryId",
  s3Link: "S3BucketLink",
} as const;

export const ROUTES = {
  api: "/api",
  summary: "/summary",
  detail: "/detail",
  health: "/health",
} as const;
export const STATUS = {
  ok: 200,
  badRequest: 400,
  notFound: 404,
  internal: 500,
} as const;
export const ERRORS = {
  invalidRequest: {
    code: "INVALID_REQUEST",
    message: "The request is invalid.",
  },
  notFound: {
    code: "SUMMARY_NOT_FOUND",
    message: "This summary could not be found.",
  },
  routeNotFound: {
    code: "NOT_FOUND",
    message: "The requested resource could not be found.",
  },
  internal: {
    code: "INTERNAL_ERROR",
    message: "Reports are temporarily unavailable. Please try again.",
  },
} as const;
export const DEFAULTS = {
  host: "127.0.0.1",
  port: 3000,
  region: "ap-southeast-1",
  frontendPath: "../frontend/dist",
  connectionTimeout: 3000,
  requestTimeout: 10000,
  maxAttempts: 2,
  maxSummaryBytes: 1048576,
  shutdownTimeout: 15000,
  jsonLimit: "8kb",
} as const;
