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

from .http import Client, SourceError, REFRESH_CACHE_TTL
from .model import (OPEN_ABSTRACT_LICENSES, attach_openalex, biorxiv_paper, crossref_paper,
                    doi, exact_date, normalize_work, subtract_months, validate_snapshot)
from .readership import validated_imports
from .biorxiv_usage import refresh_reference
from .published_usage import collect_plos, refresh_elife

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
        retrieved_at = data.get("_retrieved_at", stamp)
        for row in rows:
            identifier = doi(row.get("doi"))
            if not identifier or row.get("category") != "neuroscience" or row.get("server", "biorxiv").lower() != "biorxiv":
                continue
            version = str(row.get("version", ""))
            if not version.isdigit() or not exact_date(row.get("date")):
                continue
            entry = state["preprints"].setdefault(identifier, {"versions": {}, "observed_at": stamp})
            entry["versions"][version] = safe_bio(row)
            entry["observed_at"] = retrieved_at
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
        state["preprints"][identifier]["observed_at"] = data.get("_retrieved_at", stamp)
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
            paper = crossref_paper(row, journal, data.get("_retrieved_at", stamp))
            if paper:
                old = state["published"].get(paper["id"],{})
                for key in ("accesses","downloads","elife_vor_verified","vor_date","reviewed_preprint_date","publication_history"):
                    if key in old:
                        paper[key] = old[key]
                if paper.get("vor_date"):
                    paper["date"] = paper["vor_date"]
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
    aliases = {}
    for identifier in identifiers:
        old = cache.get(identifier, {})
        canonical = old.get("doi") or identifier
        aliases.setdefault(canonical, []).append(identifier)
        # Migrate the earlier boolean marker into a bounded retry timestamp.
        if old.get("alias_checked") and not old.get("alias_checked_at"):
            old["alias_checked_at"] = old.get("checked_at")
    canonical_dois = sorted(aliases)
    for offset in range(0, len(canonical_dois), 75):
        batch = canonical_dois[offset:offset + 75]
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
                normalized = normalize_work(row, result.get("_retrieved_at", stamp))
                for alias in aliases.get(identifier, [identifier]):
                    cache[alias] = copy.deepcopy(normalized)
                found.add(identifier)
        for canonical in batch:
            if canonical not in found:
                # A missing match is unmeasured, never a zero or deletion of last-good data.
                for identifier in aliases[canonical]:
                    if identifier not in cache:
                        cache[identifier] = {"_not_found": True, "checked_at": stamp}
                    else:
                        cache[identifier]["checked_at"] = stamp
                    checked = cache[identifier].get("alias_checked_at")
                    if not checked or (datetime.fromisoformat(stamp.replace("Z", "+00:00")) -
                                       datetime.fromisoformat(checked.replace("Z", "+00:00"))).days >= 7:
                        missing.append(identifier)
        report["rows"] += len(rows)
    # Resolve a bounded queue of DOI aliases/merged versions with free singletons.
    missing.sort(key=lambda identifier: (cache[identifier].get("alias_checked_at") or "", identifier))
    for identifier in missing[:75]:
        result = client.get("https://api.openalex.org/works/https://doi.org/" + identifier +
                            "?select=id,doi,cited_by_count,topics,keywords")
        if not result.get("_not_found"):
            cache[identifier] = normalize_work(result, result.get("_retrieved_at", stamp))
        cache[identifier]["alias_checked"] = True
        cache[identifier]["alias_checked_at"] = result.get("_retrieved_at", stamp)
        report["alias_lookups"] = report.get("alias_lookups", 0) + 1
    report["unmatched"] = sum(cache.get(d, {"_not_found": True}).get("_not_found", False) for d in identifiers)
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
        if not attach_openalex(p, work if work and not work.get("_not_found") else None, config):
            excluded["non_neuroscience_or_unknown_topics"] += 1
        elif p["journal_id"] == "elife" and not p.get("elife_vor_verified"):
            excluded["elife_vor_unverified_or_reviewed_preprint"] += 1
        else:
            papers.append(p)
    for paper in papers:
        nature = state.get("nature_readership", {}).get(paper["id"])
        if nature:
            from .nature_import import validate_measurement
            validate_measurement(nature,paper["id"],paper["journal_id"])
        m = nature or state.get("readership", {}).get(paper["id"]) or (state.get("reference_readership", {}).get(paper["id"]) if paper["kind"] == "preprint" else None)
        if m:
            paper["accesses"] = m
            paper["provenance"].append({"source":m["source"],"url":m["permission_url"],"observed_at":m["observed_at"],
                                        "license":"Public numerical usage facts; upstream code and paper text excluded" if m.get("provider")=="biorxiv-top-numeric" else m.get("permission_license","Provider-authorized numerical reuse")})
        if paper["kind"]=="published" and paper["accesses"]["value"] is not None:
            measured = paper["accesses"]
            paper["provenance"].append({"source":measured.get("attribution",measured["source"]),"url":measured["source_url"],
                                        "observed_at":measured["observed_at"],"license":measured.get("permission_license","Public API with required attribution")})
    papers.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    by_source = Counter(p["journal_id"] for p in papers)
    from adapters.nature_article import NATURE_JOURNALS
    nature_papers = [p for p in papers if p["journal_id"] in NATURE_JOURNALS]
    nature_measured = [p for p in nature_papers if p["accesses"]["value"] is not None]
    nature_report = state["sources"].get("nature-offline-import",{})
    nature_module = {"module":"offline-import","live_fetch_enabled":False,
                    "status":"partial" if nature_measured else "awaiting-authorized-data",
                    "measured":len(nature_measured),"total":len(nature_papers),
                    "approximate":sum(p["accesses"].get("approximate",False) for p in nature_measured),
                    "last_import":nature_report.get("last_success"),"errors":nature_report.get("errors",[])}
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
                              "measured_accesses":sum(p["accesses"]["value"] is not None for p in papers if p["journal_id"]==j["id"]),
                              "oldest": min((p["date"] for p in papers if p["journal_id"] == j["id"]), default=None),
                              "newest": max((p["date"] for p in papers if p["journal_id"] == j["id"]), default=None)} for j in config["journals"]]}
    return {"schema_version": 1, "generated_at": stamp, "papers": papers, "coverage": counts,
            "sources": list(state["sources"].values()),
            "readership": {"status": "partial" if counts["accesses"] else "unavailable", "measured": counts["accesses"],
                           "reason": "Partial raw readership: available bioRxiv monthly views+PDF facts; PLOS source-defined all-time views; eLife all-version page views. These sources count different events and windows",
                           "source": state["sources"].get("biorxiv-top-numeric"),
                           "nature": nature_module,
                           "disabled_adapters": config["disabled_adapters"]},
            "schedule": {"metadata_hours": 6, "citations": "daily", "repair": "weekly",
                         "last_citations": state.get("last_citations"), "last_repair": state.get("last_repair")}}


def run(mode="auto", root=ROOT, client=None):
    client = client or Client()
    config = json.loads((root / "config/sources.json").read_text())
    state_path = root / "data/state.json.gz"
    state = read_state(state_path)
    import_path = root / "data/readership.json"
    imports = json.loads(import_path.read_text()) if import_path.exists() else []
    state["readership"] = validated_imports(imports, config["readership_providers"])
    stamp, today = stamp_now(), datetime.now(timezone.utc).date()
    year_start = subtract_months(today, 12).isoformat()
    end = today.isoformat()
    sync_upgrade = state.get("openalex_sync_version") != 2
    last_repair = state.get("last_repair", "")
    repair_due = not last_repair or date.fromisoformat(last_repair[:10]).isocalendar()[:2] != today.isocalendar()[:2]
    repair = mode in {"repair", "backfill"} or (mode == "auto" and repair_due)
    citations = mode in {"backfill", "repair", "citations"} or (mode == "auto" and (sync_upgrade or state.get("last_citations", "")[:10] != end))
    metadata = mode != "citations"
    if metadata:
        tasks = [("biorxiv", None)] + [(j["id"], j) for j in config["journals"]]
        for name, journal in tasks:
            previous = state["sources"].get(name, {})
            full_success = previous.get("last_full_success")
            full_due = not full_success or date.fromisoformat(full_success[:10]).isocalendar()[:2] != today.isocalendar()[:2]
            last_success = previous.get("last_success")
            schema_current = not (journal and journal.get("metadata_api")=="plos") or previous.get("source_schema_version")==2
            if mode=="auto" and schema_current and previous.get("status")=="ok" and full_success and last_success and previous.get("requested_end")==end and not (repair and full_due) and datetime.now(timezone.utc)-datetime.fromisoformat(last_success.replace("Z","+00:00")) < REFRESH_CACHE_TTL:
                print(json.dumps({"source":name,"cached":True,"last_success":last_success}),flush=True)
                continue  # Code deploys/queue repair do not multiply recent successful metadata calls.
            source_start = year_start if not full_success or (journal and journal.get("metadata_api")=="plos") or mode in {"repair", "backfill"} or (repair and full_due) else (today - timedelta(days=8)).isoformat()
            report = source_report(name, previous, stamp_now(), source_start, end)
            try:
                if journal and journal.get("metadata_api")=="plos":
                    collect_plos(client,journal,source_start,end,state,stamp,report)
                elif journal:
                    collect_crossref(client, journal, source_start, end, state, stamp, report)
                else:
                    collect_biorxiv(client, source_start, end, state, stamp, report)
                report["last_success"] = stamp_now()
                if source_start == year_start:
                    report["last_full_success"] = report["last_success"]
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
    targets = [d for d in identifiers if d not in state["openalex"] or
               (citations and (sync_upgrade or mode in {"repair", "backfill", "citations"} or state["openalex"][d].get("checked_at", "")[:10] != end))]
    report = source_report("openalex", state["sources"].get("openalex", {}), stamp_now(), year_start, end)
    report["requested_dois"] = len(targets)
    if targets:
        try:
            refresh_openalex(client, targets, state["openalex"], stamp, report)
            report["last_success"] = stamp_now()
            if citations:
                state["last_citations"] = report["last_success"]
                state["openalex_sync_version"] = 2
        except (SourceError, ValueError) as error:
            report["status"] = "partial" if report["rows"] else "failed"
            report["errors"].append(str(error))
        state["sources"]["openalex"] = report
    if repair and all(s["status"] == "ok" for s in state["sources"].values()):
        state["last_repair"] = stamp_now()
    state["openalex"] = {d: w for d, w in state["openalex"].items() if d in identifiers}
    if "openalex" in state["sources"]:
        state["sources"]["openalex"]["unmatched"] = sum(state["openalex"].get(d, {"_not_found": True}).get("_not_found", False) for d in identifiers)
    refresh_reference(client,state,config)
    if metadata:
        refresh_elife(client,state,config,stamp_now(),year_start,end)
    snapshot = make_snapshot(state, config, stamp_now(), year_start, end)
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
