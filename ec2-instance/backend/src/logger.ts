import type { Config } from "./config.js";

export function createLogger(level: Config["LOG_LEVEL"]) {
  return {
    info(message: string) {
      if (level === "info")
        console.info(JSON.stringify({ level: "info", message }));
    },
    error(message: string, error?: unknown) {
      if (level === "silent") return;
      // Do not serialize SDK responses or request bodies: they may contain credentials/content.
      console.error(
        JSON.stringify({
          level: "error",
          message,
          errorType: error instanceof Error ? error.name : "UnknownError",
          detail: error instanceof Error ? error.message : undefined,
        }),
      );
    },
  };
}
export type Logger = ReturnType<typeof createLogger>;
