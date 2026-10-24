import { z } from "zod";
import { ATTRIBUTES } from "./constants.js";

const nonempty = z.string().refine((value) => value.trim().length > 0);
const summaryId = nonempty.refine(
  (value) => Buffer.byteLength(value, "utf8") <= 2048,
);
const httpUrl = z.url().refine((value) => {
  const url = new URL(value);
  return (
    ["http:", "https:"].includes(url.protocol) && !url.username && !url.password
  );
});

export const reportMetadataSchema = z.object({
  [ATTRIBUTES.releaseDate]: z.iso.date(),
  [ATTRIBUTES.reportLink]: httpUrl,
  [ATTRIBUTES.summaryId]: summaryId,
});
export const reportRecordSchema = reportMetadataSchema.extend({
  [ATTRIBUTES.s3Link]: nonempty,
});
export const summarySchema = z
  .object({ title: nonempty, body: nonempty })
  .strict();
export const detailRequestSchema = z
  .object({ hansardSummaryId: summaryId })
  .strict();
export const listRequestSchema = z.object({}).strict().optional();
export type ReportMetadata = z.infer<typeof reportMetadataSchema>;
export type Summary = z.infer<typeof summarySchema>;
