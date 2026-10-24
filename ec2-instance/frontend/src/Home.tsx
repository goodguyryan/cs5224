import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "./api";
import type { ReportMetadata } from "./api";
import { COPY, ROUTES, SETTINGS } from "./constants";
import { Arrow, ErrorState, Loading } from "./components";
import { useResource } from "./useResource";

const dateFormatter = new Intl.DateTimeFormat("en-SG", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

function ArchiveTable({ reports }: { reports: ReportMetadata[] }) {
  const [search, setSearch] = useSearchParams();
  const tableTop = useRef<HTMLDivElement>(null);
  const sorted = [...reports].sort(
    (a, b) =>
      b.DateOfRelease.localeCompare(a.DateOfRelease) ||
      a.HansardReportSummaryId.localeCompare(b.HansardReportSummaryId),
  );
  const pages = Math.max(1, Math.ceil(sorted.length / SETTINGS.pageSize));
  const requestedPage = Number(search.get("page") || 1);
  const page =
    Number.isSafeInteger(requestedPage) && requestedPage > 0
      ? Math.min(pages, requestedPage)
      : 1;
  const start = (page - 1) * SETTINGS.pageSize;
  const visible = sorted.slice(start, start + SETTINGS.pageSize);
  function goTo(next: number) {
    const params = new URLSearchParams(search);
    if (next === 1) params.delete("page");
    else params.set("page", String(next));
    setSearch(params, { preventScrollReset: true });
    tableTop.current?.scrollIntoView({ behavior: "instant", block: "start" });
    tableTop.current?.focus({ preventScroll: true });
  }
  if (reports.length === 0)
    return (
      <div className="state-panel">
        <span className="empty-symbol" aria-hidden="true">
          —
        </span>
        <h3>{COPY.emptyTitle}</h3>
        <p>{COPY.emptyBody}</p>
      </div>
    );
  return (
    <div ref={tableTop} tabIndex={-1} className="archive-table-wrap">
      <div className="table-scroll">
        <table>
          <caption className="sr-only">{COPY.tableCaption}</caption>
          <thead>
            <tr>
              {Object.values(COPY.columns).map((label) => (
                <th scope="col" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((report, index) => (
              <tr key={report.HansardReportSummaryId}>
                <td className="row-number">
                  {String(start + index + 1).padStart(2, "0")}
                </td>
                <td className="release-date">
                  <time dateTime={report.DateOfRelease}>
                    {dateFormatter.format(
                      new Date(`${report.DateOfRelease}T00:00:00Z`),
                    )}
                  </time>
                </td>
                <td>
                  <a
                    href={report.ActualReportLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="source-link"
                  >
                    {COPY.official}
                    <Arrow diagonal />
                    <span className="sr-only"> {COPY.newTab}</span>
                  </a>
                </td>
                <td>
                  <Link
                    className="read-link"
                    to={`${ROUTES.summaryPrefix}${encodeURIComponent(report.HansardReportSummaryId)}`}
                  >
                    {COPY.read}
                    <Arrow />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <p aria-live="polite">
          {COPY.showing}{" "}
          <strong>
            {start + 1}–{start + visible.length}
          </strong>{" "}
          {COPY.of} {reports.length} {COPY.reports}
        </p>
        <nav aria-label={COPY.paginationLabel}>
          <button onClick={() => goTo(page - 1)} disabled={page === 1}>
            <Arrow left />
            <span>{COPY.previous}</span>
          </button>
          <span className="page-indicator">
            {COPY.page} <strong>{page}</strong> {COPY.of} {pages}
          </span>
          <button onClick={() => goTo(page + 1)} disabled={page === pages}>
            <span>{COPY.next}</span>
            <Arrow />
          </button>
        </nav>
      </div>
    </div>
  );
}

export default function Home() {
  const { state, retry } = useResource("archive", api.list);
  useEffect(() => {
    document.title = COPY.brand;
  }, []);
  return (
    <>
      <main id="main-content">
        <section className="hero shell">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="red-line" />
              {COPY.heroEyebrow}
            </p>
            <h1>
              {COPY.heroTitle}
              <br />
              <em>{COPY.heroAccent}</em>
            </h1>
            <p className="hero-description">{COPY.heroDescription}</p>
            <a href="#archive" className="button primary">
              {COPY.browse}
              <Arrow />
            </a>
            <p className="hero-note">{COPY.heroNote}</p>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="art-orbit orbit-one" />
            <div className="art-orbit orbit-two" />
            <div className="editorial-card">
              <div className="card-top">
                <span>{COPY.featureLabel}</span>
                <span className="card-star">✳</span>
              </div>
              <div className="card-architecture">
                <svg viewBox="0 0 260 150" fill="none">
                  <path
                    d="m30 52 100-40 100 40M20 62h220M40 120h180M30 132h200M58 74v35m36-35v35m36-35v35m36-35v35m36-35v35"
                    stroke="currentColor"
                    strokeWidth="3"
                  />
                  <path d="M36 52h188" stroke="currentColor" />
                </svg>
              </div>
              <h2>{COPY.featureTitle}</h2>
              <p>{COPY.featureDescription}</p>
              <div className="card-bottom">
                {COPY.featureIndex}
                <span>↗</span>
              </div>
            </div>
            <div className="five-seal">
              <strong>{COPY.sealNumber}</strong>
              <span>{COPY.sealLabel}</span>
            </div>
          </div>
        </section>
        <section id="about" className="about-section">
          <div className="shell">
            <h2 className="sr-only">{COPY.aboutTitle}</h2>
            <div className="features">
              {COPY.features.map((feature) => (
                <div className="feature" key={feature.number}>
                  <span className="feature-number">{feature.number}</span>
                  <div>
                    <h3>{feature.title}</h3>
                    <p>{feature.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section id="archive" className="archive-section shell">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{COPY.archiveEyebrow}</p>
              <h2>{COPY.archiveTitle}</h2>
              <p>{COPY.archiveDescription}</p>
            </div>
            <span className="archive-tag">
              <span className="status-dot" />
              {COPY.archiveTag}
            </span>
          </div>
          {state.status === "loading" && (
            <Loading label={COPY.loadingArchive} />
          )}
          {state.status === "error" && <ErrorState archive retry={retry} />}
          {state.status === "success" && <ArchiveTable reports={state.data} />}
        </section>
      </main>
    </>
  );
}
