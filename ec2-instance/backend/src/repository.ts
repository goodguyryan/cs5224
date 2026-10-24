import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  GetCommand,
  ScanCommand,
} from "@aws-sdk/lib-dynamodb";
import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { NodeHttpHandler } from "@smithy/node-http-handler";
import { Readable } from "node:stream";
import type { Config } from "./config.js";
import { ATTRIBUTES } from "./constants.js";
import {
  reportMetadataSchema,
  reportRecordSchema,
  summarySchema,
} from "./schemas.js";
import type { ReportMetadata, Summary } from "./schemas.js";

export interface ReportRepository {
  list(): Promise<ReportMetadata[]>;
  detail(id: string): Promise<Summary | null>;
  close(): void;
}

export function parseS3Location(
  location: string,
  allowedBucket: string,
  region: string,
) {
  const url = new URL(location);
  if (url.username || url.password || url.port || url.hash)
    throw new Error("Invalid S3 location.");
  let bucket: string;
  let key: string;
  if (url.protocol === "s3:" && !url.search) {
    bucket = url.hostname;
    key = decodeURIComponent(url.pathname.slice(1));
  } else if (url.protocol === "https:") {
    const suffix = region.startsWith("cn-")
      ? "amazonaws.com.cn"
      : "amazonaws.com";
    const endpoints = [`s3.${region}.${suffix}`, `s3-${region}.${suffix}`];
    if (region === "us-east-1") endpoints.push("s3.amazonaws.com");
    if (endpoints.includes(url.hostname)) {
      const [encodedBucket, ...parts] = url.pathname.slice(1).split("/");
      bucket = decodeURIComponent(encodedBucket ?? "");
      key = decodeURIComponent(parts.join("/"));
    } else if (
      endpoints.some((host) => url.hostname === `${allowedBucket}.${host}`)
    ) {
      bucket = allowedBucket;
      key = decodeURIComponent(url.pathname.slice(1));
    } else {
      throw new Error(
        "S3 location must use a standard endpoint in the configured region.",
      );
    }
  } else {
    throw new Error("Unsupported S3 location.");
  }
  if (bucket !== allowedBucket || !key)
    throw new Error("S3 location is outside the configured summary bucket.");
  return { Bucket: bucket, Key: key };
}

export function createRepository(config: Config): ReportRepository {
  const clientOptions = {
    region: config.AWS_REGION,
    maxAttempts: config.AWS_MAX_ATTEMPTS,
    requestHandler: new NodeHttpHandler({
      connectionTimeout: config.AWS_CONNECTION_TIMEOUT_MS,
      requestTimeout: config.AWS_REQUEST_TIMEOUT_MS,
      throwOnRequestTimeout: true,
    }),
  };
  const rawDynamo = new DynamoDBClient(clientOptions);
  const dynamo = DynamoDBDocumentClient.from(rawDynamo);
  // Give each AWS client its own connection pool.
  const s3 = new S3Client({
    ...clientOptions,
    requestHandler: new NodeHttpHandler({
      connectionTimeout: config.AWS_CONNECTION_TIMEOUT_MS,
      requestTimeout: config.AWS_REQUEST_TIMEOUT_MS,
      throwOnRequestTimeout: true,
    }),
  });

  return {
    async list() {
      const reports: ReportMetadata[] = [];
      let cursor: Record<string, unknown> | undefined;
      do {
        const page = await dynamo.send(
          new ScanCommand({
            TableName: config.DYNAMODB_TABLE_NAME,
            ProjectionExpression: "#date, #link, #id",
            ExpressionAttributeNames: {
              "#date": ATTRIBUTES.releaseDate,
              "#link": ATTRIBUTES.reportLink,
              "#id": ATTRIBUTES.summaryId,
            },
            ExclusiveStartKey: cursor,
          }),
        );
        for (const item of page.Items ?? [])
          reports.push(reportMetadataSchema.parse(item));
        cursor = page.LastEvaluatedKey;
      } while (cursor && Object.keys(cursor).length > 0);
      return reports;
    },
    async detail(id) {
      const result = await dynamo.send(
        new GetCommand({
          TableName: config.DYNAMODB_TABLE_NAME,
          Key: { [ATTRIBUTES.summaryId]: id },
          ConsistentRead: true,
        }),
      );
      if (!result.Item) return null;
      const record = reportRecordSchema.parse(result.Item);
      const location = parseS3Location(
        record.S3BucketLink,
        config.S3_SUMMARY_BUCKET,
        config.AWS_REGION,
      );
      // Bound the complete download, including stream consumption, across SDK retries.
      const signal = AbortSignal.timeout(
        config.AWS_REQUEST_TIMEOUT_MS * config.AWS_MAX_ATTEMPTS,
      );
      const object = await s3.send(new GetObjectCommand(location), {
        abortSignal: signal,
      });
      if (!(object.Body instanceof Readable))
        throw new Error("S3 did not return a readable body.");
      const stream = object.Body;
      const abort = () =>
        stream.destroy(new Error("S3 summary download timed out."));
      signal.addEventListener("abort", abort, { once: true });
      try {
        if (signal.aborted) throw new Error("S3 summary download timed out.");
        if ((object.ContentLength ?? 0) > config.MAX_SUMMARY_BYTES)
          throw new Error("S3 summary exceeds size limit.");
        const chunks: Buffer[] = [];
        let size = 0;
        for await (const chunk of stream) {
          const buffer = Buffer.isBuffer(chunk)
            ? chunk
            : Buffer.from(chunk as Uint8Array);
          size += buffer.length;
          if (size > config.MAX_SUMMARY_BYTES)
            throw new Error("S3 summary exceeds size limit.");
          chunks.push(buffer);
        }
        const json = JSON.parse(
          new TextDecoder("utf-8", { fatal: true }).decode(
            Buffer.concat(chunks),
          ),
        ) as unknown;
        summarySchema.parse(json);
        return json as Summary;
      } finally {
        signal.removeEventListener("abort", abort);
        stream.destroy();
      }
    },
    close() {
      rawDynamo.destroy();
      s3.destroy();
    },
  };
}
