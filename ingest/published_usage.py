"""GPL-3.0-only. Permitted PLOS and eLife APIs; source-defined raw counts."""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone, timedelta

from .http import SourceError
from .model import base_paper, clean_text, doi, exact_date, metric, timestamp_valid, attach_openalex

PLOS_POLICY = "https://api.plos.org/api-display-policy/"
ELIFE_POLICY = "https://github.com/elifesciences/developer-resources"


def stamp_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def array(value):
    return value if isinstance(value, list) else [value] if value is not None else []


def plos_paper(row: dict, journal: dict, stamp: str) -> dict | None:
    """Reject partial document fragments and verify exact publisher ISSNs."""
    if row.get("doc_type") != "full" or row.get("doc_partial_parent_id"):
        return None
    identifier = doi(row.get("id"))
    issns = set(array(row.get("eissn")) + array(row.get("pissn"))) & set(journal["issns"])
    published = row.get("publication_date")
    day = exact_date(published[:10]) if isinstance(published, str) and timestamp_valid(published) else None
    titles = array(row.get("title_display"))
    subjects = [clean_text(s) for s in array(row.get("subject"))]
    if not identifier or not issns or not day or not titles or "Neuroscience" not in subjects:
        return None
    p = base_paper(identifier, "published", titles[0], array(row.get("author_display")), day,
                   journal["id"], journal["name"], stamp, "PLOS publication_date (publisher API)")
    p["issns"] = sorted(issns)
    p["publisher_categories"] = subjects
    p["classification"] = {"method":"pending OpenAlex topics", "evidence":"PLOS subject: Neuroscience", "automatic":True}
    query_url = "https://api.plos.org/search?" + urllib.parse.urlencode({"q":f'id:"{identifier}" AND doc_type:full',"rows":1,"wt":"json"})
    p["provenance"] = [{"source":"Data Provided by PLOS", "url":query_url, "observed_at":stamp,
                         "license":"PLOS API reuse with attribution"}]
    p["accesses"] = metric(row.get("counter_total_all"), stamp, "PLOS Search API", provider="plos-api",
        permission_url=PLOS_POLICY, definition="PLOS source-defined total views, all time", aggregation="cumulative",
        attribution="Data Provided by PLOS", source_url=query_url,
        recent_30_days=metric(row.get("counter_total_month"),stamp,"PLOS Search API",window="last 30 days (source-defined)"),
        source_indexed_at=row.get("timestamp") if timestamp_valid(row.get("timestamp")) else None,
        zero_caveat="Source-reported zero may reflect an index awaiting metrics; it does not mean nobody read the paper")
    return p


def collect_plos(client, journal, start, end, state, stamp, report):
    offset, seen_pages, seen_dois = 0, set(), set()
    # One publisher query supplies metadata and fresh cumulative metrics together.
    query = (f'eissn:"{journal["issns"][0]}" AND subject:"Neuroscience" AND doc_type:full '
             'AND -doc_partial_parent_id:[* TO *] AND article_type:"Research Article" '
             f'AND publication_date:[{start}T00:00:00Z TO {end}T23:59:59Z]')
    while True:
        params = {"q":query,"fl":"id,title_display,author_display,publication_date,eissn,pissn,subject,doc_type,doc_partial_parent_id,counter_total_all,counter_total_month,timestamp",
                  "sort":"publication_date desc,id asc","rows":100,"start":offset,"wt":"json"}
        payload = client.get("https://api.plos.org/search?" + urllib.parse.urlencode(params))
        response = payload.get("response", {})
        rows, total = response.get("docs"), response.get("numFound")
        if not isinstance(rows, list) or isinstance(total,bool) or not isinstance(total,int) or total < 0:
            raise SourceError("Unexpected PLOS search response")
        if not rows:
            if offset < total:
                raise SourceError("PLOS returned an incomplete page")
            break
        signature = tuple(r.get("id") for r in rows)
        if signature in seen_pages:
            raise SourceError("Repeated PLOS page; cached records retained")
        seen_pages.add(signature)
        report["rows"] += len(rows)
        observed = payload.get("_retrieved_at",stamp)
        for row in rows:
            paper = plos_paper(row,journal,observed)
            if not paper or not start <= paper["date"] <= end or paper["id"] in seen_dois:
                report["excluded"]["fragments_invalid_or_duplicate"] = report["excluded"].get("fragments_invalid_or_duplicate",0)+1
                continue
            seen_dois.add(paper["id"])
            old = state["published"].get(paper["id"])
            if old and paper["accesses"]["value"] is None and old["accesses"]["value"] is not None:
                paper["accesses"] = old["accesses"]
            state["published"][paper["id"]] = paper
        offset += len(rows)
        if offset >= total:
            break
        if len(seen_pages) >= 70:
            raise SourceError("PLOS page budget reached; remaining rows deferred")
    report["pages"] = len(seen_pages)
    report["unique_dois"] = len(seen_dois)


def elife_id(identifier: str) -> str | None:
    match = re.fullmatch(r"10\.7554/elife\.(\d+)(?:\.\d+)?",doi(identifier) or "")
    return match[1] if match else None


def elife_history(payload: dict, article_id: str) -> dict:
    versions = payload.get("versions")
    if not isinstance(versions,list):
        raise ValueError("eLife version history missing")
    vor_dates, reviewed_dates, history = [], [], []
    for row in versions:
        identifier = doi(row.get("doi") or row.get("uri"))
        if row.get("status") == "vor" and row.get("stage") == "published" and elife_id(identifier) == article_id:
            published = row.get("published")
            if not timestamp_valid(published) or not exact_date(published[:10]):
                raise ValueError("eLife VOR publication date is invalid")
            vor_dates.append(published[:10])
            history.append({"status":"vor","doi":identifier,"date":published[:10]})
        elif row.get("status") == "preprint":
            published = row.get("date")
            if identifier and timestamp_valid(published) and exact_date(published[:10]):
                history.append({"status":"reviewed-preprint" if elife_id(identifier)==article_id else "preprint",
                                "doi":identifier,"date":published[:10]})
                if elife_id(identifier)==article_id:
                    reviewed_dates.append(published[:10])
    return {"vor_date":min(vor_dates) if vor_dates else None,
            "reviewed_preprint_date":min(reviewed_dates) if reviewed_dates else None,
            "publication_history":sorted(history,key=lambda v:(v["date"],v["doi"]))}


def elife_measurement(payload: dict, article_id: str, channel: str, stamp: str) -> dict:
    if channel not in {"page-views","downloads"} or "totalValue" not in payload:
        raise ValueError("eLife cumulative metric missing")
    # totalValue is the complete cumulative source count, not the first page sum.
    return metric(payload["totalValue"],stamp,"eLife public API",provider="elife-api",permission_url=ELIFE_POLICY,
        definition="eLife page views, all versions (including reviewed preprints before VOR)" if channel=="page-views" else "eLife downloads, all versions",
        aggregation="cumulative",source_url=f"https://api.elifesciences.org/metrics/article/{article_id}/{channel}?by=month&per-page=1",
        attribution="Data from eLife", version_scope="All eLife versions; may precede VOR publication", unique_readers=False)


def refresh_elife(client,state,config,stamp,start,end,limit=350):
    if not any(j["id"]=="elife" for j in config["journals"]):
        return
    old_report = state["sources"].get("elife-api",{})
    report = {"id":"elife-api","status":"ok","checked_at":stamp,"last_success":old_report.get("last_success"),
              "requested_start":start,"requested_end":end,"rows":0,"errors":[],"reviewed_preprint_only":0,"deferred":0}
    cache = state.setdefault("elife_history",{})
    candidates = [p for p in state["published"].values() if p["journal_id"]=="elife" and
                  attach_openalex(dict(p),state["openalex"].get(p["id"]) if not state["openalex"].get(p["id"],{}).get("_not_found") else None,config)]
    candidates.sort(key=lambda p:(p["accesses"].get("observed_at") or "",p["id"]))
    processed = 0
    for paper in candidates:
        article_id = elife_id(paper["id"])
        if not article_id:
            continue
        cached = cache.get(article_id)
        if cached:
            paper.update({k:v for k,v in cached.items() if k!="checked_at"})
            paper["elife_vor_verified"] = bool(cached["vor_date"])
            if cached["vor_date"]:
                paper["date"] = cached["vor_date"]
                paper["date_source"] = "eLife first published VOR, verified by version history"
            paper["provenance"] = [x for x in paper["provenance"] if x["source"]!="eLife version history"] + [{
                "source":"eLife version history","url":f"https://api.elifesciences.org/articles/{article_id}/versions",
                "observed_at":cached["checked_at"],"license":"eLife public API reuse"}]
        observed = paper["accesses"].get("observed_at")
        if observed and datetime.fromisoformat(stamp.replace("Z","+00:00"))-datetime.fromisoformat(observed.replace("Z","+00:00")) < timedelta(hours=6):
            continue
        if processed >= limit:
            report["deferred"] += 1
            continue
        processed += 1
        try:
            # Verify new/recent histories; weekly revisit older histories through the bounded queue.
            history_ttl = timedelta(days=7) if cached and cached["vor_date"] else timedelta(hours=6)
            if not cached or datetime.fromisoformat(stamp.replace("Z","+00:00"))-datetime.fromisoformat(cached["checked_at"].replace("Z","+00:00")) >= history_ttl:
                payload = client.get(f"https://api.elifesciences.org/articles/{article_id}/versions")
                parsed = elife_history(payload,article_id)
                cache[article_id] = {**parsed,"checked_at":payload.get("_retrieved_at",stamp)}
                paper.update(parsed)
                paper["elife_vor_verified"] = bool(parsed["vor_date"])
                if parsed["vor_date"]:
                    paper["date"] = parsed["vor_date"]
                paper["provenance"] = [x for x in paper["provenance"] if x["source"]!="eLife version history"] + [{
                    "source":"eLife version history","url":f"https://api.elifesciences.org/articles/{article_id}/versions",
                    "observed_at":payload.get("_retrieved_at",stamp),"license":"eLife public API reuse"}]
                report["last_success"] = stamp_now()
            if not paper.get("elife_vor_verified"):
                report["reviewed_preprint_only"] += 1
                continue
            paper["date_source"] = "eLife first published VOR, verified by version history"
            views = client.get(f"https://api.elifesciences.org/metrics/article/{article_id}/page-views?by=month&per-page=1")
            measured = elife_measurement(views,article_id,"page-views",views.get("_retrieved_at",stamp))
            if measured["value"] is not None:
                paper["accesses"] = measured
            downloads = client.get(f"https://api.elifesciences.org/metrics/article/{article_id}/downloads?by=month&per-page=1")
            measured = elife_measurement(downloads,article_id,"downloads",downloads.get("_retrieved_at",stamp))
            if measured["value"] is not None:
                paper["downloads"] = measured
            report["rows"] += 1
            report["last_success"] = stamp_now()
        except (SourceError,ValueError) as error:
            report["status"] = "partial" if report["rows"] or old_report.get("last_success") else "failed"
            if len(report["errors"]) < 5:
                report["errors"].append(str(error))
            # One host failure stops this serial queue; last-good observations survive.
            break
    if report["deferred"] and report["status"]=="ok":
        report["status"] = "partial"
        report["errors"].append("Bounded eLife queue has deferred records")
    state["sources"]["elife-api"] = report
