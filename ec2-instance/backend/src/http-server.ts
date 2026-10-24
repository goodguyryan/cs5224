import type { Config } from "./config.js";
import type { Logger } from "./logger.js";
import type { ReportRepository } from "./repository.js";
import { createApp } from "./app.js";
import { DEFAULTS } from "./constants.js";

export function startServer(
  config: Config,
  repository: ReportRepository,
  logger: Logger,
) {
  const app = createApp(config, repository, logger);
  const server = app.listen(config.PORT, config.HOST, () => {
    logger.info(
      `Parliament in Five listening on http://${config.HOST}:${config.PORT}`,
    );
  });
  server.on("error", (error) => {
    logger.error("HTTP server failed", error);
    repository.close();
    process.exitCode = 1;
  });
  let stopping = false;
  const shutdown = () => {
    if (stopping) return;
    stopping = true;
    logger.info("Shutting down");
    const deadline = setTimeout(() => {
      server.closeAllConnections();
      repository.close();
      process.exit(1);
    }, DEFAULTS.shutdownTimeout).unref();
    server.close(() => {
      clearTimeout(deadline);
      repository.close();
    });
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
  return server;
}
