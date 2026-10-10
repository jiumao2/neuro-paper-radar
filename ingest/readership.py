"""Optional, explicitly permitted readership imports; production defaults to disabled."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from .model import doi, metric, timestamp_valid


def validate_import(record: dict, providers: list[dict]) -> dict:
    provider = next((p for p in providers if p["id"] == record.get("provider")), None)
    if not provider or not provider.get("enabled") or not provider.get("redistribution_allowed"):
        raise ValueError("Readership provider has no recorded collection/republication permission")
    permission = provider.get("permission_url", "")
    if urlsplit(permission).scheme != "https" or not urlsplit(permission).hostname:
        raise ValueError("Provider permission evidence must be an HTTPS source URL")
    if not doi(record.get("doi")) or not timestamp_valid(record.get("observed_at")):
        raise ValueError("Invalid readership DOI/timestamp")
    observed = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
    if observed > datetime.now(timezone.utc):
        raise ValueError("Readership observation cannot be in the future")
    if record.get("aggregation") not in {"cumulative", "window"} or not record.get("definition"):
        raise ValueError("Readership definition and aggregation are required")
    if record["aggregation"] == "window" and not all(record.get(k) for k in ("window_start", "window_end")):
        raise ValueError("Windowed counts need a declared window")
    if record.get("value") is None:
        raise ValueError("A missing import must not overwrite a last-good measurement")
    return metric(record.get("value"), record["observed_at"], provider["name"],
                  provider=provider["id"], permission_url=permission,
                  definition=record["definition"], aggregation=record["aggregation"],
                  window_start=record.get("window_start"), window_end=record.get("window_end"))


def validated_imports(records: list[dict], providers: list[dict]) -> dict:
    """Latest observation replaces a previous cumulative/window snapshot; never sum."""
    result = {}
    for record in records:
        measurement = validate_import(record, providers)
        identifier = doi(record["doi"])
        previous = result.get(identifier)
        if previous is None or datetime.fromisoformat(measurement["observed_at"].replace("Z", "+00:00")) > datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00")):
            result[identifier] = measurement
    return result


def main():
    import argparse
    import json
    from pathlib import Path
    from .refresh import atomic_bytes

    parser = argparse.ArgumentParser(description="Import an explicitly permitted readership JSON file")
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "config/sources.json").read_text())
    records = json.loads(Path(args.file).read_text())
    if not isinstance(records, list):
        raise ValueError("Readership import must be an array")
    target = root / "data/readership.json"
    previous = json.loads(target.read_text()) if target.exists() else []
    # Validate everything before touching persistent imports.
    measurements = validated_imports(previous + records, config["readership_providers"])
    atomic_bytes(target, (json.dumps(previous + records, ensure_ascii=False, indent=2) + "\n").encode())
    print(f"Imported {len(measurements)} permitted DOI measurements; run metadata refresh to publish")


class ApprovedReadershipQueue:
    """Serial queue extension point. Disabled adapters cannot enqueue any requests."""
    def __init__(self, provider: dict, sleeper, interval: float = 1.0):
        if not provider.get("enabled") or not provider.get("redistribution_allowed") or not provider.get("permission_url"):
            raise ValueError("Provider is disabled or lacks recorded permission")
        if interval < 1:
            raise ValueError("Readership queue must be rate limited")
        self.provider, self.sleep, self.interval = provider, sleeper, interval

    def process(self, records, fetch):
        results = []
        for i, identifier in enumerate(records):
            if i:
                self.sleep(self.interval)
            row = fetch(identifier)
            results.append((identifier, validate_import(row, [self.provider])))
        return results


if __name__ == "__main__":
    main()
