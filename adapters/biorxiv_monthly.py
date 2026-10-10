"""Independent monthly readership ledger. No network calls or production samples.

Numeric fixtures exercise the architecture while bioRxiv route/reuse verification
is pending. This module does not activate a scraper or infer daily readership.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from ingest.model import doi, metric, timestamp_valid


def monthly_rows(rows: list[dict], observed_at: str) -> dict:
    if not timestamp_valid(observed_at):
        raise ValueError("A timezone-aware observation timestamp is required")
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    months = {}
    for row in rows:
        month = str(row.get("month", ""))
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValueError("Month must contain an explicit year")
        first = date(int(month[:4]), int(month[5:]), 1)
        if first > observed.date() or month in months:
            raise ValueError("Future or duplicate monthly rows are not valid")
        fulltext, pdf = row.get("fulltext"), row.get("pdf")
        metric(fulltext); metric(pdf)
        months[month] = {"fulltext": fulltext, "pdf": pdf, "observed_at": observed_at}
    return months


class MonthlyLedger:
    def __init__(self, records=None):
        self.records = records or {}

    def apply(self, identifier: str, rows: list[dict], observed_at: str, *, scope: str):
        identifier = doi(identifier)
        if not identifier or scope != "all_versions":
            raise ValueError("A verified DOI and explicitly consolidated all-version scope are required")
        # Validate the full response before changing last-good monthly records.
        incoming = monthly_rows(rows, observed_at)
        record = self.records.setdefault(identifier, {})
        for month, values in incoming.items():
            previous = record.get(month)
            if not previous or datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(observed_at.replace("Z", "+00:00")):
                record[month] = values  # Replace a revised month; never add snapshots.

    def summary(self, identifier: str) -> dict:
        record = self.records.get(doi(identifier), {})
        months = sorted(record)
        fulltext = sum(record[m]["fulltext"] for m in months) if months and all(record[m]["fulltext"] is not None for m in months) else None
        pdf = sum(record[m]["pdf"] for m in months) if months and all(record[m]["pdf"] is not None for m in months) else None
        value = fulltext + pdf if fulltext is not None and pdf is not None else None
        return {"value": value, "fulltext": fulltext, "pdf": pdf, "reported_months": months,
                "period_start_month": months[0] if months else None,
                "period_end_month": months[-1] if months else None,
                "observed_at": max((record[m]["observed_at"] for m in months), default=None),
                "definition": "Reported monthly full-text views + PDF downloads; events, not unique readers",
                "scope": "all_versions", "missing_months_are_zero": False,
                "daily_events_inferred": False}
