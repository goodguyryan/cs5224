"""Direct SPRS JSON requests, bounded retries, and request pacing."""

from __future__ import annotations

import json
import time
from datetime import date
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .models import FetchedJSON
from .parser import parse_sitting_date, validate_sitting

SEARCH_PAGE = "https://sprs.parl.gov.sg/search/"
SEARCH_URL = SEARCH_PAGE + "searchResult"
SITTING_URL = SEARCH_PAGE + "getHansardReport"


class HansardClientError(RuntimeError):
    pass


class _NoSearchResults(HansardClientError):
    """SPRS returned its specific empty-search response using HTTP 500."""


def _is_empty_search_error(request: Request, error: HTTPError) -> bool:
    if request.full_url != SEARCH_URL or error.code != 500:
        return False
    try:
        payload = json.loads(error.read(8192).decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, OSError):
        return False
    return (
        isinstance(payload, dict)
        and type(payload.get("errorCode")) is int
        and payload["errorCode"] == 0
        and payload.get("description") == "No Results Found"
    )


class HansardClient:
    def __init__(self, *, timeout: float = 20, retries: int = 2, delay: float = 1) -> None:
        self.timeout = timeout
        self.retries = max(1, retries)
        self.delay = max(0, delay)
        self._opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self._last_finished: float | None = None

    def _request(self, request: Request) -> bytes:
        for attempt in range(self.retries):
            if self._last_finished is not None:
                wait = self.delay - (time.monotonic() - self._last_finished)
                if wait > 0:
                    time.sleep(wait)
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    return response.read()
            except HTTPError as error:
                no_results = _is_empty_search_error(request, error)
                error.close()
                if no_results:
                    raise _NoSearchResults("SPRS search returned no results") from error
                if (error.code < 500 and error.code != 429) or attempt + 1 == self.retries:
                    raise HansardClientError(f"SPRS HTTP {error.code}: {request.full_url}") from error
            except (URLError, OSError) as error:
                if attempt + 1 == self.retries:
                    raise HansardClientError(f"SPRS request failed: {error}") from error
            finally:
                self._last_finished = time.monotonic()
            time.sleep(2 ** attempt)
        raise HansardClientError("SPRS request attempts exhausted")

    def _post_json(self, url: str, payload: dict[str, Any]) -> FetchedJSON:
        headers = {
            "User-Agent": "ParliamentInFive/0.3 (+educational project)",
            "Accept": "application/json",
            "Referer": SEARCH_PAGE,
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, method="POST", headers={
            **headers, "Content-Type": "application/json",
        })
        raw_bytes = self._request(request)
        try:
            return FetchedJSON(json.loads(raw_bytes.decode("utf-8-sig")), raw_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HansardClientError(f"SPRS returned invalid JSON: {url}") from error

    def has_sitting(self, day: date) -> bool:
        # These fields reproduce the portal's search form; only dates change.
        payload = {
            "keyword": "undefined",
            "fromday": f"{day.day:02d}", "frommonth": f"{day.month:02d}",
            "fromyear": str(day.year),
            "today": f"{day.day:02d}", "tomonth": f"{day.month:02d}",
            "toyear": str(day.year),
            "dateRange": "custom", "startIndex": "0", "endIndex": "0",
            "footNoteChecked": "false", "lang": "", "ministrySelected": [],
            "mpName": "", "parliamentNo": "", "portfolio": [],
            "reportContent": "with all the words", "rsSelected": "",
            "selectedSort": "date_dt desc", "titleChecked": "false",
        }
        try:
            result = self._post_json(SEARCH_URL, payload)
        except _NoSearchResults:
            return False
        if not isinstance(result.payload, list):
            raise HansardClientError("searchResult did not return a list")
        if not result.payload:
            return False
        for row in result.payload:
            if not isinstance(row, dict) or not row.get("sittingDate"):
                raise HansardClientError("searchResult row is missing sittingDate")
            if parse_sitting_date(row["sittingDate"]) == day.isoformat():
                return True
        raise HansardClientError("searchResult returned dates outside the requested day")

    def fetch_sitting(self, day: date) -> FetchedJSON:
        result = self._post_json(SITTING_URL, {"sittingDate": day.strftime("%d-%m-%Y")})
        validate_sitting(result.payload, requested_date=day.isoformat())
        return result
