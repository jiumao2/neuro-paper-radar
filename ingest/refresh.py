"""Official API refresh with durable last-good state and explicit partial coverage."""
from __future__ import annotations

import argparse
import copy
import gzip
import json
import os
import tempfile
import urllib.parse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .http import Client, SourceError
from .model import (OPEN_ABSTRACT_LICENSES, attach_openalex, biorxiv_paper, crossref_paper,
                    doi, exact_date, normalize_work, subtract_months, validate_snapshot)

ROOT = Path(__file__).resolve().parents[1]
BIO_FIELDS = {"doi", "title", "authors", "date", "version", "license", "category", "published", "server"}


def stamp_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_bio(row):
    result = {k: row[k] for k in BIO_FIELDS if k in row}
    if str(row.get("license", "")).lower() in OPEN_ABSTRACT_LICENSES:
        result["abstract"] = row.get("abstract", "")
    return result


def source_report(name, previous, stamp, start, end):
    return {"id": name, "status": "ok", "checked_at": stamp,
            "last_success": previous.get("last_success"), "last_full_success": previous.get("last_full_success"), "requested_start": start,
            "requested_end": end, "rows": 0, "excluded": {}, "errors": []}


def collect_biorxiv(client, start, end, state, stamp, report):
    cursor, seen_pages = 0, set()
    changed = set()
    while True:
        url = f"https://api.biorxiv.org/details/biorxiv/{start}/{end}/{cursor}?category=neuroscience"
        data = client.get(url)
        messages = data.get("messages", [])
        message = messages[0] if messages else {}
        rows = data.get("collection")
        if not isinstance(rows, list) or message.get("status") not in {"ok", "OK"}:
            raise SourceError("Unexpected bioRxiv page or API status")
        if not rows:
            break
        signature = tuple((r.get("doi"), str(r.get("version"))) for r in rows)
        if signature in seen_pages:
            raise SourceError("Repeated bioRxiv page; pagination stopped")
        seen_pages.add(signature)
        report["rows"] += len(rows)
        for row in rows:
            identifier = doi(row.get("doi"))
            if not identifier or row.get("category") != "neuroscience" or row.get("server", "biorxiv").lower() != "biorxiv":
                continue
            version = str(row.get("version", ""))
            if not version.isdigit() or not exact_date(row.get("date")):
                continue
            entry = state["preprints"].setdefault(identifier, {"versions": {}, "observed_at": stamp})
            entry["versions"][version] = safe_bio(row)
            entry["observed_at"] = stamp
            changed.add(identifier)
        cursor += len(rows)  # Use the actual page size, not an assumed 30/100.
        total = message.get("total")
        if str(total).isdigit() and cursor >= int(total):
            break
        if len(seen_pages) >= 600:
            raise SourceError("bioRxiv page budget exhausted; partial data retained")
    # A revised paper returned in the date interval may have v1 outside it.
    missing_v1 = [d for d in sorted(changed) if "1" not in state["preprints"][d]["versions"]]
    for identifier in missing_v1[:150]:
        data = client.get(f"https://api.biorxiv.org/details/biorxiv/{identifier}")
        for row in data.get("collection", []):
            version = str(row.get("version", ""))
            if doi(row.get("doi")) == identifier and row.get("category") == "neuroscience" and version.isdigit():
                state["preprints"][identifier]["versions"][version] = safe_bio(row)
    report["excluded"]["unresolved_v1"] = sum("1" not in state["preprints"][d]["versions"] for d in changed)
    report["pages"] = len(seen_pages)


def collect_crossref(client, journal, start, end, state, stamp, report):
    cursor, seen = "*", set()
    selected = "DOI,title,author,published-online,ISSN,type"
    while True:
        params = {"filter": f"from-online-pub-date:{start},until-online-pub-date:{end},type:journal-article",
                  "rows": 1000, "cursor": cursor, "select": selected}
        url = f"https://api.crossref.org/journals/{journal['issns'][0]}/works?{urllib.parse.urlencode(params)}"
        data = client.get(url)
        message = data.get("message", {})
        rows = message.get("items")
        if not isinstance(rows, list):
            raise SourceError("Unexpected Crossref response")
        if not rows:
            break
        signature = tuple(row.get("DOI") for row in rows)
        if signature in seen:
            raise SourceError("Repeated Crossref page; partial data retained")
        seen.add(signature)
        report["rows"] += len(rows)
        for row in rows:
            paper = crossref_paper(row, journal, stamp)
            if paper:
                state["published"][paper["id"]] = paper
            else:
                report["excluded"]["invalid_or_imprecise_online_date"] = report["excluded"].get("invalid_or_imprecise_online_date", 0) + 1
        next_cursor = message.get("next-cursor")
        if len(rows) < 1000 or not next_cursor:
            break
        cursor = next_cursor
        if len(seen) > 60:
            raise SourceError("Crossref page budget exhausted")
    report["api_total"] = message.get("total-results")


def refresh_openalex(client, identifiers, cache, stamp, report):
    # 75 values stay below the supported OR limit (100) and bound URL length.
    missing = []
    for offset in range(0, len(identifiers), 75):
        batch = identifiers[offset:offset + 75]
        params = {"filter": "doi:" + "|".join("https://doi.org/" + d for d in batch),
                  "per_page": 100, "select": "id,doi,cited_by_count,topics,keywords"}
        result = client.get("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        rows = result.get("results")
        if not isinstance(rows, list):
            raise SourceError("Unexpected OpenAlex response")
        found = set()
        for row in rows:
            identifier = doi(row.get("doi"))
            if identifier:
                cache[identifier] = normalize_work(row, stamp)
                found.add(identifier)
        for identifier in batch:
            if identifier not in found:
                # A missing match is unmeasured, never a zero or deletion of last-good data.
                if identifier not in cache:
                    cache[identifier] = {"_not_found": True, "checked_at": stamp}
                else:
                    cache[identifier]["checked_at"] = stamp
                if cache[identifier].get("_not_found") and not cache[identifier].get("alias_checked"):
                    missing.append(identifier)
        report["rows"] += len(rows)
    # Resolve a bounded queue of DOI aliases/merged versions with free singletons.
    for identifier in missing[:75]:
        result = client.get("https://api.openalex.org/works/https://doi.org/" + identifier +
                            "?select=id,doi,cited_by_count,topics,keywords")
        if not result.get("_not_found"):
            cache[identifier] = normalize_work(result, stamp)
        cache[identifier]["alias_checked"] = True
        report["alias_lookups"] = report.get("alias_lookups", 0) + 1
    report["unmatched"] = sum(cache.get(d, {}).get("_not_found", True) for d in identifiers)
    report["aliases_deferred"] = max(0, len(missing) - 75)


def read_state(path):
    if not path.exists():
        return {"version": 1, "preprints": {}, "published": {}, "openalex": {}, "sources": {}}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        state = json.load(stream)
    if state.get("version") != 1:
        raise ValueError("Unsupported ingestion state")
    return state


def atomic_bytes(path: Path, body: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(prefix=".refresh-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def make_snapshot(state, config, stamp, start, end):
    papers = []
    excluded = Counter()
    for entry in state["preprints"].values():
        p = biorxiv_paper(list(entry["versions"].values()), entry["observed_at"])
        if not p:
            excluded["preprint_v1_unverified"] += 1
            continue
        if not start <= p["date"] <= end:
            continue
        work = state["openalex"].get(p["id"])
        attach_openalex(p, work if work and not work.get("_not_found") else None, config)
        papers.append(p)
    candidates = Counter()
    for original in state["published"].values():
        if not start <= original["date"] <= end:
            continue
        p = copy.deepcopy(original)
        candidates[p["journal_id"]] += 1
        work = state["openalex"].get(p["id"])
        if attach_openalex(p, work if work and not work.get("_not_found") else None, config):
            papers.append(p)
        else:
            excluded["non_neuroscience_or_unknown_topics"] += 1
    papers.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    by_source = Counter(p["journal_id"] for p in papers)
    counts = {"preprints": sum(p["kind"] == "preprint" for p in papers),
              "published": sum(p["kind"] == "published" for p in papers),
              "total": len(papers), "accesses": sum(p["accesses"]["value"] is not None for p in papers),
              "citations": sum(p["citations"]["value"] is not None for p in papers),
              "topics": sum(bool(p["topics"]) for p in papers),
              "abstracts": sum(bool(p["abstract"]) for p in papers),
              "requested_start": start, "requested_end": end, "excluded": dict(excluded),
              "oldest": min((p["date"] for p in papers), default=None),
              "newest": max((p["date"] for p in papers), default=None),
              "by_journal": [{**j, "count": by_source[j["id"]], "candidates": candidates[j["id"]],
                              "oldest": min((p["date"] for p in papers if p["journal_id"] == j["id"]), default=None),
                              "newest": max((p["date"] for p in papers if p["journal_id"] == j["id"]), default=None)} for j in config["journals"]]}
    return {"schema_version": 1, "generated_at": stamp, "papers": papers, "coverage": counts,
            "sources": list(state["sources"].values()),
            "readership": {"status": "unavailable", "measured": 0,
                           "reason": "No approved per-paper publisher-access feed is configured",
                           "disabled_adapters": config["disabled_adapters"]},
            "schedule": {"metadata_hours": 6, "citations": "daily", "repair": "weekly",
                         "last_citations": state.get("last_citations"), "last_repair": state.get("last_repair")}}


def run(mode="auto", root=ROOT, client=None):
    client = client or Client()
    config = json.loads((root / "config/sources.json").read_text())
    state_path = root / "data/state.json.gz"
    state = read_state(state_path)
    stamp, today = stamp_now(), datetime.now(timezone.utc).date()
    year_start = subtract_months(today, 12).isoformat()
    end = today.isoformat()
    last_repair = state.get("last_repair", "")
    repair_due = not last_repair or date.fromisoformat(last_repair[:10]).isocalendar()[:2] != today.isocalendar()[:2]
    repair = mode in {"repair", "backfill"} or (mode == "auto" and repair_due)
    citations = mode in {"backfill", "repair", "citations"} or (mode == "auto" and state.get("last_citations", "")[:10] != end)
    start = year_start if repair else (today - timedelta(days=8)).isoformat()
    metadata = mode != "citations"
    if metadata:
        tasks = [("biorxiv", None)] + [(j["id"], j) for j in config["journals"]]
        for name, journal in tasks:
            previous = state["sources"].get(name, {})
            full_success = previous.get("last_full_success")
            full_due = not full_success or date.fromisoformat(full_success[:10]).isocalendar()[:2] != today.isocalendar()[:2]
            source_start = year_start if mode in {"repair", "backfill"} or (repair and full_due) else (today - timedelta(days=8)).isoformat()
            report = source_report(name, previous, stamp, source_start, end)
            try:
                if journal:
                    collect_crossref(client, journal, source_start, end, state, stamp, report)
                else:
                    collect_biorxiv(client, source_start, end, state, stamp, report)
                report["last_success"] = stamp
                if source_start == year_start:
                    report["last_full_success"] = stamp
            except (SourceError, ValueError) as error:
                report["status"] = "partial" if report["rows"] else "failed"
                report["errors"].append(str(error))
            state["sources"][name] = report
            print(json.dumps({"source": name, "status": report["status"], "rows": report["rows"], "errors": report["errors"]}), flush=True)
    # Bound retention by the same rolling calendar-year window used by the app.
    state["published"] = {d: p for d, p in state["published"].items() if p["date"] >= year_start}
    state["preprints"] = {d: p for d, p in state["preprints"].items()
                          if "1" not in p["versions"] or p["versions"]["1"].get("date", "") >= year_start}
    identifiers = sorted(set(state["published"]) | set(state["preprints"]))
    targets = identifiers if citations else [d for d in identifiers if d not in state["openalex"]]
    report = source_report("openalex", state["sources"].get("openalex", {}), stamp, year_start, end)
    report["requested_dois"] = len(targets)
    if targets:
        try:
            refresh_openalex(client, targets, state["openalex"], stamp, report)
            report["last_success"] = stamp
            if citations:
                state["last_citations"] = stamp
        except (SourceError, ValueError) as error:
            report["status"] = "partial" if report["rows"] else "failed"
            report["errors"].append(str(error))
        state["sources"]["openalex"] = report
    if repair and all(s["status"] == "ok" for s in state["sources"].values()):
        state["last_repair"] = stamp
    state["openalex"] = {d: w for d, w in state["openalex"].items() if d in identifiers}
    snapshot = make_snapshot(state, config, stamp, year_start, end)
    validate_snapshot(snapshot, config)
    # State and public snapshot are written only after validation; prior content survives invalid refreshes.
    atomic_bytes(state_path, gzip.compress(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0))
    atomic_bytes(root / "public/data/papers.json", json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode())
    atomic_bytes(root / "data/coverage.json", (json.dumps({k: v for k, v in snapshot.items() if k != "papers"}, ensure_ascii=False, indent=2) + "\n").encode())
    print(json.dumps({"coverage": snapshot["coverage"], "requests": client.requests}, ensure_ascii=False), flush=True)
    return snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "metadata", "citations", "repair", "backfill"], default="auto")
    args = parser.parse_args()
    data = run(args.mode)
    if not data["papers"]:
        raise SystemExit("No verified production records; deployment must wait for source recovery")


if __name__ == "__main__":
    main()
