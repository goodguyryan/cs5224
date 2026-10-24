import { z } from "zod";
import { COPY, SETTINGS } from "./constants";

const nonempty = z.string().refine((text) => text.trim().length > 0);
const metadataSchema = z
  .object({
    DateOfRelease: z.iso.date(),
    ActualReportLink: z.url().refine((value) => {
      const url = new URL(value);
      return (
        ["https:", "http:"].includes(url.protocol) &&
        !url.username &&
        !url.password
      );
    }),
    HansardReportSummaryId: nonempty,
  })
  .strict();
const summarySchema = z.object({ title: nonempty, body: nonempty }).strict();
export type ReportMetadata = z.infer<typeof metadataSchema>;
export type Summary = z.infer<typeof summarySchema>;

function configuration() {
  const base = (import.meta.env.VITE_API_BASE_URL || SETTINGS.apiBase).replace(
    /\/+$/,
    "",
  );
  const timeout = Number(
    import.meta.env.VITE_API_TIMEOUT_MS || SETTINGS.timeout,
  );
  const url = new URL(base, window.location.origin);
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.search ||
    url.hash ||
    url.username ||
    url.password ||
    !Number.isInteger(timeout) ||
    timeout <= 0 ||
    timeout > SETTINGS.timeoutMaximum
  ) {
    throw new Error(COPY.configurationError);
  }
  return { base, timeout };
}

async function post<T>(
  endpoint: string,
  schema: z.ZodType<T>,
  signal: AbortSignal,
  body?: object,
): Promise<T> {
  const { base, timeout } = configuration();
  const response = await fetch(`${base}/${endpoint}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.any([signal, AbortSignal.timeout(timeout)]),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(COPY.requestError);
  const parsed = schema.safeParse((await response.json()) as unknown);
  if (!parsed.success) throw new Error(COPY.invalidResponse);
  return parsed.data;
}

export const api = {
  list: (signal: AbortSignal) =>
    post("summary", z.array(metadataSchema), signal),
  detail: (id: string, signal: AbortSignal) =>
    post("detail", summarySchema, signal, { hansardSummaryId: id }),
};
