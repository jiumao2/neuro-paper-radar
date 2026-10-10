"""Join only factual monthly counts from the independent public reference snapshot.

Upstream code, titles, authors, abstracts, and publication dates are not copied.
Direct bioRxiv metrics pages are never requested by this adapter.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from adapters.biorxiv_monthly import monthly_rows
from .http import SourceError
from .model import doi, exact_date, metric, timestamp_valid

REPO = "RobertoDF/biorxiv-top"
REF_URL = f"https://api.github.com/repos/{REPO}/git/ref/heads/data"
PROVIDER = "biorxiv-top-numeric"


def numeric_snapshot(payload: dict, commit: str, retrieved_at: str) -> tuple[dict, dict]:
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or not timestamp_valid(retrieved_at):
        raise ValueError("Invalid source commit/retrieval timestamp")
    if payload.get("category") != "neuroscience" or not exact_date(payload.get("start")) or not exact_date(payload.get("end")):
        raise ValueError("Unexpected reference cohort metadata")
    try:
        updated = datetime.strptime(payload["updated"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("Reference snapshot update timestamp is missing") from error
    papers = payload.get("papers")
    if not isinstance(papers, list):
        raise ValueError("Reference snapshot has no paper array")
    seen, measurements = set(), {}
    source_url = f"https://github.com/{REPO}/blob/{commit}/usage.json"
    for paper in papers:
        identifier = doi(paper.get("doi"))
        if not identifier or identifier in seen:
            raise ValueError("Invalid or duplicate reference DOI")
        seen.add(identifier)
        usage, fetched = paper.get("usage"), paper.get("fetched")
        if fetched is not None and not exact_date(fetched):
            raise ValueError("Invalid upstream collection date")
        if usage is None or usage == {}:
            continue  # Missing is not measured zero.
        if not isinstance(usage, dict):
            raise ValueError("Unexpected monthly usage shape")
        rows = []
        for month, values in usage.items():
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError("Monthly usage must be [fulltext, PDF]")
            rows.append({"month":month,"fulltext":values[0],"pdf":values[1]})
        ledger = monthly_rows(rows, retrieved_at)
        if any(row[channel] is None for row in ledger.values() for channel in ("fulltext","pdf")):
            continue
        fulltext = sum(row["fulltext"] for row in ledger.values())
        pdf = sum(row["pdf"] for row in ledger.values())
        months = sorted(ledger)
        measurements[identifier] = metric(fulltext+pdf,retrieved_at,"biorxiv-top public numeric snapshot",provider=PROVIDER,
            permission_url=source_url,definition="Sum of available monthly full-text views + PDF downloads; events, not unique readers",
            aggregation="reported_months",fulltext=fulltext,pdf=pdf,reported_months=months,
            upstream_fetched_date=fetched,upstream_updated_at=updated,source_commit=commit,source_url=source_url,
            lifetime_complete=False,version_coverage_verified=False,missing_months_are_zero=False)
    return measurements, {"id":PROVIDER,"status":"ok","checked_at":retrieved_at,"last_success":retrieved_at,
        "rows":len(papers),"measured_upstream":len(measurements),"requested_start":payload["start"],"requested_end":payload["end"],
        "upstream_updated_at":updated,"source_commit":commit,"source_url":source_url,"errors":[]}


def refresh_reference(client, state: dict, config: dict):
    provider = next((p for p in config["readership_providers"] if p["id"] == PROVIDER), None)
    if not provider or not provider.get("enabled"):
        return
    old_report = state["sources"].get(PROVIDER, {})
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        ref = client.get(REF_URL)
        commit = ref.get("object", {}).get("sha", "")
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise SourceError("Reference data branch has no valid commit")
        if commit == state.get("readership_source_commit"):
            state["sources"][PROVIDER] = {**old_report,"checked_at":stamp,"status":"ok","errors":[]}
            return
        payload = client.get(f"https://raw.githubusercontent.com/{REPO}/{commit}/usage.json")
        measurements, report = numeric_snapshot(payload,commit,payload.get("_retrieved_at",stamp))
        # Entire incoming snapshot is validated before replacing any cached measurement.
        state.setdefault("reference_readership", {}).update(measurements)
        state["readership_source_commit"] = commit
        state["sources"][PROVIDER] = report
    except (SourceError, ValueError) as error:
        state["sources"][PROVIDER] = {"id":PROVIDER,"status":"failed","checked_at":stamp,
            "last_success":old_report.get("last_success"),"rows":0,"requested_start":old_report.get("requested_start",stamp[:10]),
            "requested_end":old_report.get("requested_end",stamp[:10]),"errors":[str(error)],
            "source_commit":old_report.get("source_commit")}
