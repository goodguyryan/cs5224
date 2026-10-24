import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import dotenv from "dotenv";
import { z } from "zod";
import { DEFAULTS } from "./constants.js";

export const backendRoot = fileURLToPath(new URL("../", import.meta.url));
dotenv.config({ path: resolve(backendRoot, ".env"), quiet: true });

const positiveInteger = (fallback: number, maximum = 2147483647) =>
  z.coerce.number().int().positive().max(maximum).default(fallback);
const settings = z.object({
  NODE_ENV: z.enum(["development", "production"]).default("development"),
  HOST: z.string().trim().min(1).default(DEFAULTS.host),
  PORT: positiveInteger(DEFAULTS.port, 65535),
  AWS_REGION: z
    .string()
    .regex(/^[a-z]{2}(?:-[a-z]+)+-\d+$/)
    .default(DEFAULTS.region),
  DYNAMODB_TABLE_NAME: z.string().regex(/^[A-Za-z0-9_.-]{3,255}$/),
  S3_SUMMARY_BUCKET: z.string().regex(/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/),
  FRONTEND_DIST_PATH: z.string().trim().min(1).default(DEFAULTS.frontendPath),
  AWS_CONNECTION_TIMEOUT_MS: positiveInteger(DEFAULTS.connectionTimeout, 60000),
  AWS_REQUEST_TIMEOUT_MS: positiveInteger(DEFAULTS.requestTimeout, 120000),
  AWS_MAX_ATTEMPTS: positiveInteger(DEFAULTS.maxAttempts, 5),
  MAX_SUMMARY_BYTES: positiveInteger(DEFAULTS.maxSummaryBytes, 10485760),
  LOG_LEVEL: z.enum(["info", "error", "silent"]).default("info"),
});

export function readConfig(environment: NodeJS.ProcessEnv = process.env) {
  const result = settings.safeParse(environment);
  if (!result.success) {
    const keys = [
      ...new Set(result.error.issues.map((issue) => issue.path.join("."))),
    ];
    throw new Error(
      `Invalid backend configuration: ${keys.join(", ")}. See .env.example.`,
    );
  }
  const values = result.data;
  if (
    [values.DYNAMODB_TABLE_NAME, values.S3_SUMMARY_BUCKET].some((v) =>
      v.startsWith("replace-with-"),
    )
  ) {
    throw new Error(
      "Set DYNAMODB_TABLE_NAME and S3_SUMMARY_BUCKET to real resource names in backend/.env.",
    );
  }
  return {
    ...values,
    FRONTEND_DIST_PATH: resolve(backendRoot, values.FRONTEND_DIST_PATH),
  };
}
export type Config = ReturnType<typeof readConfig>;
