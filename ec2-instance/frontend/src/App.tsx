import { useEffect } from "react";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router";
import Home from "./Home";
import Reader from "./Reader";
import { COPY, ROUTES } from "./constants";
import { Arrow, Footer, Header } from "./components";

function ScrollToPage() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
    else window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname, hash]);
  return null;
}

function NotFound() {
  useEffect(() => {
    document.title = `${COPY.notFoundTitle} | ${COPY.brand}`;
  }, []);
  return (
    <main id="main-content" className="shell not-found">
      <p className="eyebrow">{COPY.notFoundEyebrow}</p>
      <h1>{COPY.notFoundTitle}</h1>
      <p>{COPY.notFoundBody}</p>
      <Link className="button primary" to={ROUTES.home}>
        {COPY.backHome}
        <Arrow />
      </Link>
    </main>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ScrollToPage />
      <a className="skip-link" href="#main-content">
        {COPY.skip}
      </a>
      <Header />
      <Routes>
        <Route path={ROUTES.home} element={<Home />} />
        <Route path={ROUTES.summary} element={<Reader />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <Footer />
    </BrowserRouter>
  );
}
