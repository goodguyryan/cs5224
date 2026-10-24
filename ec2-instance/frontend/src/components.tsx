import { Link } from "react-router";
import { COPY, ROUTES } from "./constants";

export function Arrow({
  diagonal = false,
  left = false,
}: {
  diagonal?: boolean;
  left?: boolean;
}) {
  return (
    <span aria-hidden="true" className="arrow">
      {diagonal ? "↗" : left ? "←" : "→"}
    </span>
  );
}

export function Mark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 40 40"
      fill="none"
      className="brand-mark"
    >
      <path
        d="M7 15 20 7l13 8M9 33h22M12 19v9m8-9v9m8-9v9"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Header() {
  return (
    <header className="site-header shell">
      <Link to={ROUTES.home} className="brand">
        <Mark />
        <span>{COPY.brand}</span>
      </Link>
      <nav aria-label={COPY.brand}>
        <a href="/#archive">{COPY.navArchive}</a>
        <a href="/#about">{COPY.navAbout}</a>
      </nav>
      <span className="location">
        <span className="status-dot" />
        {COPY.country}
      </span>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="shell footer-top">
        <div>
          <Link to={ROUTES.home} className="brand">
            <Mark />
            {COPY.brand}
          </Link>
          <p>{COPY.footerDescription}</p>
        </div>
        <span className="footer-monogram" aria-hidden="true">
          {COPY.brandShort}
        </span>
      </div>
      <div className="shell footer-bottom">
        <p>{COPY.footerNote}</p>
        <p>{COPY.footerLocation}</p>
      </div>
    </footer>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="state-panel" role="status">
      <span className="loading-ring" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({
  retry,
  archive = false,
}: {
  retry: () => void;
  archive?: boolean;
}) {
  return (
    <div className="state-panel error-panel" role="alert">
      <span className="eyebrow">{COPY.errorEyebrow}</span>
      <h2>{archive ? COPY.archiveErrorTitle : COPY.errorTitle}</h2>
      <p>{COPY.errorBody}</p>
      <div className="button-row">
        <button className="button primary" onClick={retry}>
          {COPY.retry}
          <Arrow />
        </button>
        {!archive && (
          <Link className="button secondary" to={ROUTES.home}>
            {COPY.backHome}
          </Link>
        )}
      </div>
    </div>
  );
}

export function BackHome() {
  return (
    <Link className="back-link" to={ROUTES.home}>
      <Arrow left />
      {COPY.backHome}
    </Link>
  );
}
