import { readConfig } from "./config.js";
import { createLogger } from "./logger.js";
import { createRepository } from "./repository.js";
import { startServer } from "./http-server.js";

try {
  const config = readConfig();
  const logger = createLogger(config.LOG_LEVEL);
  const repository = createRepository(config);
  startServer(config, repository, logger);
} catch (error) {
  console.error(
    error instanceof Error ? error.message : "Backend startup failed.",
  );
  process.exitCode = 1;
}
