import { readConfig } from "./config.js";
import { createLogger } from "./logger.js";
import { createLocalRepository } from "./local-data.js";
import { startServer } from "./http-server.js";

try {
  const config = readConfig({
    ...process.env,
    NODE_ENV: "production",
    HOST: "127.0.0.1",
    // The shared configuration is validated, but this process never constructs AWS clients.
    DYNAMODB_TABLE_NAME: "local-preview",
    S3_SUMMARY_BUCKET: "local-preview",
  });
  const logger = createLogger(config.LOG_LEVEL);
  logger.info(
    "LOCAL PREVIEW: serving 25 fictional reports. DynamoDB and S3 are disabled in this process.",
  );
  startServer(config, createLocalRepository(), logger);
} catch (error) {
  console.error(
    error instanceof Error ? error.message : "Local preview startup failed.",
  );
  process.exitCode = 1;
}
