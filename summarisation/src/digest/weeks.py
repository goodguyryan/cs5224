"""ISO week IDs such as 2026-W41; a digest covers sittings from Monday to Sunday."""

from __future__ import annotations

import re
from datetime import date, timedelta


def week_id(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_monday(week: str) -> date:
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError(f"Expected a week such as 2026-W41, got {week!r}")
    return date.fromisoformat(f"{week}-1")


def week_dates(week: str) -> list[date]:
    monday = week_monday(week)
    return [monday + timedelta(days=offset) for offset in range(7)]


def previous_week(today: date) -> str:
    return week_id(today - timedelta(days=7))


def earlier_weeks(week: str, count: int) -> list[str]:
    monday = week_monday(week)
    return [week_id(monday - timedelta(weeks=offset)) for offset in range(1, count + 1)]


def day_label(value: str | date) -> str:
    day = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{day.day} {day:%B %Y}"
