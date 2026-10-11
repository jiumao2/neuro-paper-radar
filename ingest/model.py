from __future__ import annotations

import calendar
import html
import re
from datetime import date, datetime, timezone

DOI = re.compile(r"^10\.\d{4,9}/[^\s<>\"#?]+$", re.I)
OPEN_ABSTRACT_LICENSES = {"cc_by": "CC-BY-4.0", "cc0": "CC0-1.0", "cc_by_sa": "CC-BY-SA-4.0"}


def clean_text(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", str(value))).strip()


def doi(value: str | None) -> str | None:
    value = str(value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value if DOI.fullmatch(value) else None


def subtract_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def exact_date(value) -> str | None:
    try:
        if isinstance(value, dict):
            parts = value.get("date-parts", [[]])[0]
            if len(parts) != 3:
                return None
            return date(*parts).isoformat()
        parsed = date.fromisoformat(str(value))
        return parsed.isoformat() if str(value) == parsed.isoformat() else None
    except (TypeError, ValueError, IndexError):
        return None


def metric(value=None, observed_at=None, source=None, **extra):
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ValueError("Metric must be a nonnegative integer or missing")
    return {"value": value, "observed_at": observed_at, "source": source, **extra}


def topic_data(work: dict) -> list[dict]:
    result = []
    for topic in work.get("topics", [])[:3]:
        score = topic.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
            continue
        tid = str(topic.get("id", ""))
        if not re.fullmatch(r"https://openalex.org/T\d+", tid):
            continue
        result.append({"id": tid, "name": clean_text(topic.get("display_name", "")),
                       "score": round(score, 4), "field_id": topic.get("field", {}).get("id"),
                       "source": "OpenAlex", "automatic": True})
    return result


def normalize_work(work: dict, observed_at: str) -> dict:
    wid = str(work.get("id", ""))
    if not re.fullmatch(r"https://openalex.org/W\d+", wid):
        raise ValueError("Invalid OpenAlex work identifier")
    return {"id": wid, "doi": doi(work.get("doi")), "topics": topic_data(work),
            "keywords": [clean_text(k.get("display_name", "")) for k in work.get("keywords", [])[:12]],
            "citations": metric(work.get("cited_by_count"), observed_at, "OpenAlex", work_id=wid,
                                scope="OpenAlex work; may include merged versions"),
            "checked_at": observed_at}


def base_paper(identifier: str, kind: str, title: str, authors: list[str], first_date: str,
               journal_id: str, journal_name: str, stamp: str, source: str) -> dict:
    return {"id": identifier, "doi": identifier, "kind": kind, "title": clean_text(title),
            "authors": [clean_text(a) for a in authors if clean_text(a)],
            "date": first_date, "date_source": source, "journal_id": journal_id,
            "journal": journal_name, "article_url": "https://doi.org/" + identifier,
            "topics": [], "keywords": [], "versions": [], "related_doi": None,
            "abstract": None, "abstract_license": None, "accesses": metric(),
            "citations": metric(source="OpenAlex"), "metadata_observed_at": stamp,
            "provenance": [], "classification": {}}


def biorxiv_paper(versions: list[dict], stamp: str) -> dict | None:
    versions = sorted(versions, key=lambda r: int(r.get("version", 0)))
    first = next((r for r in versions if str(r.get("version")) == "1"), None)
    if not first or not exact_date(first.get("date")):
        return None
    latest = versions[-1]
    identifier = doi(first.get("doi"))
    if not identifier:
        return None
    p = base_paper(identifier, "preprint", latest.get("title", ""),
                   str(latest.get("authors", "")).split(";"), first["date"],
                   "biorxiv", "bioRxiv", stamp, "bioRxiv first v1 posting")
    p["versions"] = [{"version": int(v["version"]), "date": exact_date(v.get("date"))}
                     for v in versions if exact_date(v.get("date"))]
    p["related_doi"] = doi(latest.get("published"))
    p["updated_date"] = latest.get("date")
    license_id = OPEN_ABSTRACT_LICENSES.get(str(latest.get("license", "")).lower())
    if license_id and latest.get("abstract"):
        p["abstract"] = str(latest["abstract"]).strip()
        p["abstract_license"] = license_id
    p["classification"] = {"method": "bioRxiv category", "evidence": "neuroscience", "automatic": False}
    p["provenance"] = [{"source": "bioRxiv API", "url": f"https://api.biorxiv.org/details/biorxiv/{identifier}",
                         "observed_at": stamp, "license": latest.get("license", "unspecified")}]
    return p


def crossref_paper(work: dict, journal: dict, stamp: str) -> dict | None:
    identifier = doi(work.get("DOI"))
    if journal["id"] == "elife" and identifier:
        match = re.fullmatch(r"10\.7554/elife\.(\d+)(?:\.\d+)?",identifier)
        if not match:
            return None
        identifier = f"10.7554/elife.{match[1]}"
    first_date = exact_date(work.get("published-online"))
    if not identifier or not first_date or work.get("type") != "journal-article":
        return None
    if not set(work.get("ISSN", [])) & set(journal["issns"]):
        return None
    titles = work.get("title", [])
    if not titles:
        return None
    authors = [" ".join(str(a.get(k, "")) for k in ("given", "family")).strip()
               or a.get("name", "") for a in work.get("author", [])]
    p = base_paper(identifier, "published", titles[0], authors, first_date,
                   journal["id"], journal["name"], stamp, "Crossref published-online (publisher deposit)")
    p["issns"] = sorted(set(work["ISSN"]) & set(journal["issns"]))
    if journal["id"] == "elife":
        p["elife_vor_verified"] = False
    p["provenance"] = [{"source": "Crossref", "url": f"https://api.crossref.org/works/{identifier}",
                         "observed_at": stamp, "license": "Bibliographic metadata; abstracts excluded"}]
    # Crossref abstracts and publisher pages are deliberately never ingested.
    p["classification"] = {"method": "journal scope" if journal["neuroscience_only"] else "pending OpenAlex topics",
                           "evidence": ", ".join(p["issns"]), "automatic": not journal["neuroscience_only"]}
    return p


def attach_openalex(p: dict, work: dict | None, config: dict) -> bool:
    if work:
        p["topics"] = work.get("topics", [])
        p["keywords"] = work.get("keywords", [])
        p["citations"] = work["citations"]
        p["provenance"] = [x for x in p["provenance"] if x["source"] != "OpenAlex"] + [{
            "source": "OpenAlex", "url": work["id"], "observed_at": work["citations"]["observed_at"], "license": "CC0-1.0"}]
    if p["kind"] == "preprint":
        return True
    journal = next(j for j in config["journals"] if j["id"] == p["journal_id"])
    if journal["neuroscience_only"]:
        return True
    evidence = [t for t in p["topics"] if t["field_id"] == config["neuroscience_field_id"]
                and t["score"] >= config["topic_min_score"]]
    if not evidence:
        return False
    p["classification"] = {"method": "OpenAlex neuroscience field", "evidence": [t["id"] for t in evidence],
                           "field_id": config["neuroscience_field_id"], "minimum_score": config["topic_min_score"],
                           "automatic": True, "warning": "Automatic classification may omit or misclassify papers"}
    return True


def timestamp_valid(value: str | None) -> bool:
    if not value:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except (ValueError, AttributeError):
        return False


def validate_paper(p: dict):
    if doi(p.get("doi")) != p.get("id") or not exact_date(p.get("date")) or not p.get("title"):
        raise ValueError("Invalid DOI, date, or title")
    if p.get("article_url") != "https://doi.org/" + p["doi"]:
        raise ValueError("Article link must resolve the original DOI")
    if p.get("kind") not in {"preprint", "published"}:
        raise ValueError("Invalid paper kind")
    if not timestamp_valid(p.get("metadata_observed_at")) or not p.get("provenance"):
        raise ValueError("Missing provenance")
    if p.get("abstract") and p.get("abstract_license") not in OPEN_ABSTRACT_LICENSES.values():
        raise ValueError("Abstract redistribution license not established")
    for key in ("accesses", "citations"):
        m = p[key]
        metric(m["value"])
        if m["value"] is not None and (not m.get("source") or not timestamp_valid(m.get("observed_at"))):
            raise ValueError("Measured metric needs source and observation time")
        if key == "accesses" and m["value"] is not None and not all(m.get(k) for k in ("permission_url", "definition", "provider")):
            raise ValueError("Readership needs permission and definition")
        if key == "accesses" and m.get("provider") == "nature-offline-import":
            from .nature_import import validate_measurement
            validate_measurement(m,p["doi"],p["journal_id"])
    if p["kind"] == "preprint":
        v1 = next((v for v in p["versions"] if v["version"] == 1), None)
        if not v1 or v1["date"] != p["date"]:
            raise ValueError("Preprint must use first v1 date")


def validate_snapshot(data: dict, config: dict):
    if data.get("schema_version") != 1 or not timestamp_valid(data.get("generated_at")):
        raise ValueError("Invalid snapshot version/timestamp")
    seen = set()
    journals = {j["id"]: j for j in config["journals"]}
    for p in data["papers"]:
        validate_paper(p)
        if p["id"] in seen:
            raise ValueError("Duplicate paper DOI")
        seen.add(p["id"])
        if p["kind"] == "published":
            j = journals.get(p["journal_id"])
            if not j or not set(p.get("issns", [])) & set(j["issns"]):
                raise ValueError("Unverified journal identifier")
            if not j["neuroscience_only"] and p["classification"].get("method") != "OpenAlex neuroscience field":
                raise ValueError("Missing multidisciplinary classification evidence")
    if data["coverage"]["total"] != len(seen):
        raise ValueError("Coverage count mismatch")
