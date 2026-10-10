import json
from pathlib import Path

from .model import validate_snapshot

root = Path(__file__).resolve().parents[1]
data = json.loads((root / "public/data/papers.json").read_text())
validate_snapshot(data, json.loads((root / "config/sources.json").read_text()))
print(f"Validated {len(data['papers'])} records; no invented missing metrics")
