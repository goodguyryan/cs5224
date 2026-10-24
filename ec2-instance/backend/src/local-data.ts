import type { ReportRepository } from "./repository.js";
import { reportMetadataSchema, summarySchema } from "./schemas.js";

const LOCAL_DATA = {
  count: 25,
  startDate: "2026-10-20T00:00:00Z",
  dayMilliseconds: 86400000,
  reportLink: "https://sprs.parl.gov.sg/search/#/home",
  disclaimer:
    "LOCAL PREVIEW — This is fictional sample content for checking the website. It does not describe an actual parliamentary report.",
  topics: [
    {
      title: "Homes and neighbourhoods",
      body: "This sample read explores how a summary could introduce housing and community spaces. A real summary would describe the discussion accurately and preserve the context of the speakers.\n\nUse this page to check line length, paragraph spacing, and navigation. The release date is archive metadata and does not form part of this title-and-body response.\n\nReturn to the archive to explore more sample reports, or use the official-report button to visit the Parliament reports portal.",
    },
    {
      title: "Getting around Singapore",
      body: "This sample read uses transport as a placeholder topic. It demonstrates the plain-text reader without asserting that any debate or decision took place.\n\nA published report summary would help readers understand the main questions, responses, and outcomes. It would give the essentials while encouraging readers to consult the official record for the full discussion.\n\nYou can refresh this page or open its URL directly. Express serves the same built React application before the browser requests the summary by its ID.",
    },
    {
      title: "Learning and opportunities",
      body: "This sample read uses education as a placeholder topic. The text is here to make the local preview useful before DynamoDB and S3 are configured.\n\nThe browser retrieves a JSON object containing just a title and a body. Paragraph breaks in the body become readable paragraphs on the page.\n\nNo AWS requests are made in this local mode. The production server continues to retrieve real metadata from DynamoDB and summary content from S3.",
    },
  ],
} as const;

export function createLocalRepository(): ReportRepository {
  const reports = Array.from({ length: LOCAL_DATA.count }, (_, index) => {
    const topic = LOCAL_DATA.topics[index % LOCAL_DATA.topics.length];
    const id = `local-report-${String(index + 1).padStart(2, "0")}`;
    const date = new Date(
      Date.parse(LOCAL_DATA.startDate) - index * LOCAL_DATA.dayMilliseconds,
    )
      .toISOString()
      .slice(0, 10);
    return {
      metadata: reportMetadataSchema.parse({
        DateOfRelease: date,
        ActualReportLink: LOCAL_DATA.reportLink,
        HansardReportSummaryId: id,
      }),
      summary: summarySchema.parse({
        title: `Local preview ${index + 1}: ${topic.title}`,
        body: `${LOCAL_DATA.disclaimer}\n\n${topic.body}`,
      }),
    };
  });
  return {
    async list() {
      return reports.map((report) => report.metadata);
    },
    async detail(id) {
      return (
        reports.find((report) => report.metadata.HansardReportSummaryId === id)
          ?.summary ?? null
      );
    },
    close() {},
  };
}
