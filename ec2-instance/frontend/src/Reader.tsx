import { useCallback, useEffect } from "react";
import { Link, useParams } from "react-router";
import { api } from "./api";
import { COPY, ROUTES } from "./constants";
import { Arrow, BackHome, ErrorState, Loading } from "./components";
import { useResource } from "./useResource";

export default function Reader() {
  const { hansardSummaryId = "" } = useParams();
  const load = useCallback(
    (signal: AbortSignal) => api.detail(hansardSummaryId, signal),
    [hansardSummaryId],
  );
  const { state, retry } = useResource(hansardSummaryId, load);
  const title =
    state.status === "success"
      ? `${state.data.title} | ${COPY.brand}`
      : COPY.brand;
  useEffect(() => {
    document.title = title;
  }, [title]);
  return (
    <main id="main-content" className="reader-page shell">
      <BackHome />
      {state.status === "loading" && <Loading label={COPY.loadingSummary} />}
      {state.status === "error" && <ErrorState retry={retry} />}
      {state.status === "success" && (
        <article className="reader-article">
          <header className="article-header">
            <p className="eyebrow">
              <span className="red-line" />
              {COPY.readerEyebrow}
            </p>
            <h1>{state.data.title}</h1>
            <span className="reader-badge">
              <span className="status-dot" />
              {COPY.readerBadge}
            </span>
          </header>
          <div className="article-body">
            {state.data.body
              .split(/\r?\n[\t ]*\r?\n/)
              .filter((paragraph) => paragraph.trim())
              .map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
          </div>
          <footer className="article-end">
            <span className="end-mark" aria-hidden="true">
              ✳
            </span>
            <h2>{COPY.readerEnd}</h2>
            <p>{COPY.readerEndBody}</p>
            <Link className="button primary" to={ROUTES.home}>
              {COPY.browse}
              <Arrow />
            </Link>
          </footer>
        </article>
      )}
    </main>
  );
}
