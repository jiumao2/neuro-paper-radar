"""GPL-3.0-only. Authorized offline Nature facts; no network collection."""
from __future__ import annotations

import argparse
import copy
import csv
import gzip
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from adapters.nature_article import NATURE_JOURNALS, article_doi, article_url, nature_doi, parse_count, parse_html
from .model import metric, subtract_months, timestamp_valid

PROVIDER = "nature-offline-import"
LICENSES = {"CC0-1.0", "CC-BY-4.0", "LicenseRef-ExplicitPermission"}
FIELDS = {"doi", "journal_id", "accesses", "observed_at", "source_url", "source_updated_at", "source_label"}
AUTH_FIELDS = {"permission_url", "permission_basis", "license", "verified_at", "journal_ids", "collection_allowed", "redistribution_allowed"}


def now_stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def valid_time(value, upper, name):
    if not timestamp_valid(value) or datetime.fromisoformat(value.replace("Z", "+00:00")) > datetime.fromisoformat(upper.replace("Z", "+00:00")):
        raise ValueError(f"Invalid or future Nature {name} timestamp")


def validate_authorization(auth, stamp):
    if not isinstance(auth, dict) or set(auth) != AUTH_FIELDS:
        raise ValueError("Nature authorization needs the documented fields; credentials and arbitrary content are not accepted")
    if auth["collection_allowed"] is not True or auth["redistribution_allowed"] is not True:
        raise ValueError("Nature collection and public numerical redistribution permission must both be recorded")
    if not isinstance(auth["license"],str) or auth["license"] not in LICENSES:
        raise ValueError("Nature numerical data needs a supported license or documented explicit permission")
    permission = auth["permission_url"]
    if not isinstance(permission, str) or len(permission) > 2000:
        raise ValueError("Invalid Nature permission evidence URL")
    url = urlsplit(permission)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.port:
        raise ValueError("Nature permission evidence needs a public HTTPS URL without credentials or signed parameters")
    if url.hostname in {"nature.com", "www.nature.com"} and url.path in {"", "/", "/robots.txt", "/info/additional-terms", "/info/terms-and-conditions"}:
        raise ValueError("Nature homepage, robots and restrictive general terms do not establish numerical republication permission")
    if not isinstance(auth["permission_basis"], str) or not 20 <= len(auth["permission_basis"].strip()) <= 2000 or re.search(r"[<>\x00-\x1f]", auth["permission_basis"]):
        raise ValueError("Nature permission basis must identify the verified numerical collection/republication rights")
    ids = auth["journal_ids"]
    if not isinstance(ids, list) or not ids or not all(isinstance(j,str) and j in NATURE_JOURNALS for j in ids) or len(set(ids)) != len(ids):
        raise ValueError("Nature authorization must declare an exact supported journal scope")
    valid_time(auth["verified_at"], stamp, "permission verification")
    return {**auth, "permission_basis": auth["permission_basis"].strip()}


def validate_measurement(measured, identifier, journal_id, stamp=None):
    """Revalidate persisted permissions and numeric precision before publication."""
    stamp = stamp or now_stamp()
    if measured.get("provider") != PROVIDER or journal_id not in NATURE_JOURNALS or measured.get("journal_id") != journal_id:
        raise ValueError("Nature measurement journal/provider mismatch")
    identifier = nature_doi(identifier)
    if measured.get("source_url") != article_url(identifier):
        raise ValueError("Nature measurement must cite its matching ordinary article")
    if measured.get("aggregation") != "cumulative" or not measured.get("definition") or measured.get("source_label") not in {"Accesses", "Views"}:
        raise ValueError("Nature metric definition and source label are required")
    parsed = parse_count(measured.get("display_value"))
    if parsed["value"] is None or parsed["value"] != measured.get("value") or type(measured.get("approximate")) is not bool or parsed["approximate"] != measured["approximate"]:
        raise ValueError("Nature approximate display and numerical value disagree")
    valid_time(measured.get("observed_at"), stamp, "observation")
    valid_time(measured.get("imported_at"), stamp, "import")
    if measured.get("source_updated_at") is not None:
        valid_time(measured["source_updated_at"], measured["observed_at"], "source update")
    if measured.get("input_format") not in {"html", "csv", "json"} or not re.fullmatch(r"[a-f0-9]{64}", str(measured.get("import_fingerprint", ""))):
        raise ValueError("Nature local import format and fingerprint are required")
    auth = validate_authorization({"permission_url": measured.get("permission_url"),
        "permission_basis": measured.get("permission_basis"), "license": measured.get("permission_license"),
        "verified_at": measured.get("permission_verified_at"), "journal_ids": measured.get("permission_journal_ids"),
        "collection_allowed": measured.get("collection_allowed"), "redistribution_allowed": measured.get("redistribution_allowed")}, stamp)
    if journal_id not in auth["journal_ids"]:
        raise ValueError("Nature article lies outside the recorded permission scope")
    metric(measured["value"])
    return measured


def import_records(state, config, records, authorization, input_format, fingerprint, stamp=None):
    """Validate the complete batch, then replace newer DOI observations; never sum."""
    stamp = stamp or now_stamp()
    module = config.get("nature_import", {})
    if not module.get("enabled") or module.get("live_fetch_enabled") is not False:
        raise ValueError("Only the configured offline Nature import module is enabled")
    auth = validate_authorization(authorization, stamp)
    if not isinstance(records, list) or not 1 <= len(records) <= 5000:
        raise ValueError("Nature import needs 1–5000 explicit DOI records")
    if input_format not in {"html", "csv", "json"} or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise ValueError("Invalid Nature input format/fingerprint")
    existing = state.get("nature_readership", {})
    updated = copy.deepcopy(existing)
    missing, older, changed = 0, 0, 0
    journals = {j["id"]: j for j in config["journals"]}
    for row in records:
        if not isinstance(row, dict) or set(row)-FIELDS:
            raise ValueError("Nature records accept numerical facts and provenance only; paper text is excluded")
        identifier = nature_doi(row.get("doi"))
        paper = state["published"].get(identifier)
        journal_id = row.get("journal_id")
        journal = journals.get(journal_id)
        if not paper or journal_id not in NATURE_JOURNALS or journal_id not in auth["journal_ids"] or paper["journal_id"] != journal_id or not journal or not set(paper.get("issns", [])) & set(journal["issns"]):
            raise ValueError("Nature imports must match existing official metadata and its exact journal ISSNs")
        observed = row.get("observed_at")
        valid_time(observed, stamp, "observation")
        source_url = row.get("source_url") or article_url(identifier)
        if article_doi(source_url) != identifier:
            raise ValueError("Nature source URL and DOI disagree")
        source_updated = row.get("source_updated_at") or None
        if source_updated:
            valid_time(source_updated, observed, "source update")
        label = row.get("source_label") or "Accesses"
        if label not in {"Accesses", "Views"}:
            raise ValueError("Only Nature source-defined access/view counts are imported; citations remain OpenAlex")
        parsed = parse_count(row.get("accesses"))
        previous = updated.get(identifier)
        if previous:
            validate_measurement(previous, identifier, journal_id, stamp)
        if parsed["value"] is None:
            missing += 1
            continue  # Missing bars/exports never erase a real zero or its timestamp.
        measured = metric(parsed["value"], observed, "Nature authorized offline import", **{k:v for k,v in parsed.items() if k!="value"},
            provider=PROVIDER, journal_id=journal_id, definition=f"Nature source-defined cumulative {label}; abbreviated displays are approximate; events, not unique readers",
            aggregation="cumulative", source_url=article_url(identifier), source_label=label, source_updated_at=source_updated,
            imported_at=stamp, input_format=input_format, import_fingerprint=fingerprint,
            permission_url=auth["permission_url"], permission_basis=auth["permission_basis"], permission_license=auth["license"],
            permission_verified_at=auth["verified_at"], permission_journal_ids=auth["journal_ids"], collection_allowed=True, redistribution_allowed=True)
        validate_measurement(measured, identifier, journal_id, stamp)
        if previous:
            prior_time = datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00"))
            this_time = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            if this_time < prior_time:
                older += 1
                continue
            if this_time == prior_time and (previous["value"], previous["approximate"], previous["source_label"]) != (measured["value"], measured["approximate"], measured["source_label"]):
                raise ValueError("Conflicting Nature observations at the same timestamp")
        updated[identifier] = measured
        changed += 1
    # Only sanitized numerical facts and public permission references persist.
    state["nature_readership"] = updated
    prior = state["sources"].get(PROVIDER, {})
    today = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
    state["sources"][PROVIDER] = {"id": PROVIDER, "status": "partial" if missing else "ok", "checked_at": stamp,
        "last_success": stamp if changed else prior.get("last_success"), "requested_start": subtract_months(today,12).isoformat(),
        "requested_end": today.isoformat(), "rows": len(records), "updated": changed, "missing_retained": missing,
        "older_ignored": older, "errors": [f"{missing} missing counters retained their last-good measurements"] if missing else []}
    return state["sources"][PROVIDER]


def read_records(path, input_format, html_metadata=None):
    body = path.read_bytes()
    if len(body) > 20_000_000:
        raise ValueError("Nature local export exceeds the 20 MB import bound")
    text = body.decode("utf-8-sig")
    if input_format == "html":
        metadata = html_metadata or {}
        parsed = parse_html(text, metadata.get("doi"), metadata.get("source_url"))
        rows = [{**metadata, "doi": parsed["doi"], "source_url": parsed["source_url"], "accesses": parsed["display_value"], "source_label": parsed["source_label"]}]
    elif input_format == "csv":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames)-FIELDS:
            raise ValueError("Invalid or duplicate Nature CSV headers")
        rows = list(reader)
    elif input_format == "json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            if set(payload) != {"schema_version", "records"} or payload["schema_version"] != 1:
                raise ValueError("Nature JSON wrapper must use schema_version 1 and records only")
            rows = payload["records"]
        else:
            rows = payload
    else:
        raise ValueError("Only local HTML, CSV, and JSON Nature imports are supported")
    return rows, hashlib.sha256(body).hexdigest()


def import_file(root, path, authorization_path, input_format=None, html_metadata=None):
    from .refresh import read_state, make_snapshot, atomic_bytes
    from .model import validate_snapshot
    root, path, authorization_path = Path(root), Path(path), Path(authorization_path)
    input_format = input_format or {".html":"html", ".htm":"html", ".csv":"csv", ".json":"json"}.get(path.suffix.lower())
    rows, fingerprint = read_records(path, input_format, html_metadata)
    auth = json.loads(authorization_path.read_text(encoding="utf-8"))
    config = json.loads((root/"config/sources.json").read_text())
    state_path = root/"data/state.json.gz"
    state = read_state(state_path)
    stamp = now_stamp()
    report = import_records(state,config,rows,auth,input_format,fingerprint,stamp)
    today = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
    snapshot = make_snapshot(state,config,stamp,subtract_months(today,12).isoformat(),today.isoformat())
    validate_snapshot(snapshot,config)
    # Invalid inputs or snapshots leave all persistent files untouched.
    atomic_bytes(state_path,gzip.compress(json.dumps(state,ensure_ascii=False,separators=(",", ":")).encode(),mtime=0))
    atomic_bytes(root/"public/data/papers.json",json.dumps(snapshot,ensure_ascii=False,separators=(",", ":")).encode())
    atomic_bytes(root/"data/coverage.json",(json.dumps({k:v for k,v in snapshot.items() if k!="papers"},ensure_ascii=False,indent=2)+"\n").encode())
    return report


def main():
    parser = argparse.ArgumentParser(description="Import authorized local Nature numerical facts; no Nature requests are made")
    parser.add_argument("--file",required=True)
    parser.add_argument("--authorization",required=True)
    parser.add_argument("--format",choices=["html","csv","json"])
    parser.add_argument("--doi")
    parser.add_argument("--journal-id",choices=NATURE_JOURNALS)
    parser.add_argument("--observed-at")
    parser.add_argument("--source-url")
    parser.add_argument("--source-updated-at")
    args = parser.parse_args()
    metadata = {k:v for k,v in {"doi":args.doi,"journal_id":args.journal_id,"observed_at":args.observed_at,
                               "source_url":args.source_url,"source_updated_at":args.source_updated_at}.items() if v is not None}
    try:
        report = import_file(Path(__file__).resolve().parents[1],args.file,args.authorization,args.format,metadata)
    except OSError as error:
        parser.exit(2,f"Nature import could not complete local file I/O: {error}; inspect the three output files before publishing\n")
    except (ValueError,TypeError,KeyError,UnicodeError) as error:
        parser.exit(2,f"Nature import rejected; last-good files unchanged: {error}\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
