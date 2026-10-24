import express from "express";
import type { ErrorRequestHandler } from "express";
import helmet from "helmet";
import { existsSync } from "node:fs";
import { join, extname, relative, sep } from "node:path";
import type { Config } from "./config.js";
import type { ReportRepository } from "./repository.js";
import type { Logger } from "./logger.js";
import { DEFAULTS, ERRORS, ROUTES, STATUS } from "./constants.js";
import { detailRequestSchema, listRequestSchema } from "./schemas.js";

export function createApp(
  config: Config,
  repository: ReportRepository,
  logger: Logger,
) {
  const app = express();
  app.disable("x-powered-by");
  app.use(
    helmet({
      // Express serves HTTP directly; keep browser requests on the current protocol.
      contentSecurityPolicy: {
        directives: {
          upgradeInsecureRequests: null,
        },
      },
      strictTransportSecurity:
        config.NODE_ENV === "production" ? undefined : false,
    }),
  );

  const api = express.Router();
  api.use((_req, res, next) => {
    res.set("Cache-Control", "no-store");
    next();
  });
  api.use(express.json({ limit: DEFAULTS.jsonLimit }));
  api.get(ROUTES.health, (_req, res) => {
    res.json({ status: "ok" });
  });
  api.post(ROUTES.summary, async (req, res) => {
    if (
      !listRequestSchema.safeParse(req.body as unknown).success ||
      (!req.is("application/json") &&
        (Number(req.headers["content-length"] ?? 0) > 0 ||
          Boolean(req.headers["transfer-encoding"])))
    ) {
      res.status(STATUS.badRequest).json({ error: ERRORS.invalidRequest });
      return;
    }
    res.json(await repository.list());
  });
  api.post(ROUTES.detail, async (req, res) => {
    const body = detailRequestSchema.safeParse(req.body as unknown);
    if (!body.success) {
      res.status(STATUS.badRequest).json({ error: ERRORS.invalidRequest });
      return;
    }
    const summary = await repository.detail(body.data.hansardSummaryId);
    if (!summary) {
      res.status(STATUS.notFound).json({ error: ERRORS.notFound });
      return;
    }
    res.json(summary);
  });
  api.use((_req, res) => {
    res.status(STATUS.notFound).json({ error: ERRORS.routeNotFound });
  });
  app.use(ROUTES.api, api);

  const index = join(config.FRONTEND_DIST_PATH, "index.html");
  if (config.NODE_ENV === "production" && !existsSync(index)) {
    throw new Error(
      "Frontend build is missing. Run npm run build in frontend before production startup.",
    );
  }
  app.use(
    express.static(config.FRONTEND_DIST_PATH, {
      index: false,
      dotfiles: "deny",
      setHeaders(res, path) {
        res.setHeader(
          "Cache-Control",
          relative(config.FRONTEND_DIST_PATH, path).startsWith(
            `assets${sep}`,
          ) && extname(path) !== ".html"
            ? "public, max-age=31536000, immutable"
            : "no-cache",
        );
      },
    }),
  );
  app.use((req, res, next) => {
    if (req.method !== "GET" || !req.accepts("html") || !existsSync(index)) {
      next();
      return;
    }
    const knownRoute =
      req.path === "/" || /^\/summary\/[^/]+\/?$/.test(req.path);
    // Never turn a missing script/image/API path into an HTML response.
    if (!knownRoute && (extname(req.path) || req.path.startsWith("/assets/"))) {
      next();
      return;
    }
    res.set("Cache-Control", "no-cache");
    res.status(knownRoute ? STATUS.ok : STATUS.notFound).sendFile(index);
  });
  app.use((_req, res) => {
    res.status(STATUS.notFound).json({ error: ERRORS.routeNotFound });
  });
  const errors: ErrorRequestHandler = (error: unknown, _req, res, next) => {
    if (res.headersSent) {
      next(error);
      return;
    }
    const requestFailure =
      typeof error === "object" &&
      error !== null &&
      "type" in error &&
      [
        "entity.parse.failed",
        "entity.too.large",
        "encoding.unsupported",
        "charset.unsupported",
        "request.aborted",
        "request.size.invalid",
      ].includes(String(error.type));
    if (requestFailure) {
      res.status(STATUS.badRequest).json({ error: ERRORS.invalidRequest });
      return;
    }
    logger.error("Request failed", error);
    res.status(STATUS.internal).json({ error: ERRORS.internal });
  };
  app.use(errors);
  return app;
}
