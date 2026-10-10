"""Small, bounded official-API client. No proxy, identity, or credential tricks."""
from __future__ import annotations

import json
import time
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ALLOWED_HOSTS = {"api.biorxiv.org", "api.crossref.org", "api.openalex.org", "api.github.com", "raw.githubusercontent.com", "api.plos.org", "api.elifesciences.org"}


class SourceError(RuntimeError):
    pass


def retry_delay(value: str | None, attempt: int, now: datetime | None = None) -> float:
    delay = float(2 ** (attempt + 1))
    if value:
        try:
            delay = max(delay, float(value))
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                delay = max(delay, (date - (now or datetime.now(timezone.utc))).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    return delay


class Client:
    def __init__(self, opener=None, sleeper=time.sleep, clock=time.monotonic, budget=1600):
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleeper
        self.clock = clock
        self.budget = budget
        self.requests = 0
        self.host_requests: dict[str, int] = {}
        self.last: dict[str, float] = {}

    def get(self, url: str) -> dict:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username:
            raise SourceError("Endpoint is not an approved official metadata API")
        if parsed.hostname == "api.github.com" and parsed.path != "/repos/RobertoDF/biorxiv-top/git/ref/heads/data":
            raise SourceError("Only the approved public numerical reference branch may be queried")
        if parsed.hostname == "raw.githubusercontent.com" and not parsed.path.startswith("/RobertoDF/biorxiv-top/"):
            raise SourceError("Only the approved public numerical reference snapshot may be fetched")
        if parsed.hostname == "api.plos.org" and (parsed.path != "/search" or not 1 <= int(urllib.parse.parse_qs(parsed.query).get("rows",["100"])[0]) <= 100):
            raise SourceError("PLOS requests must use its documented search endpoint and at most 100 rows")
        if parsed.hostname == "api.elifesciences.org" and not re.fullmatch(r"/(?:articles/\d+/versions|metrics/article/\d+/(?:page-views|downloads))",parsed.path):
            raise SourceError("Only documented eLife version history and metric endpoints are enabled")
        host = parsed.hostname
        for attempt in range(3):
            if self.requests >= self.budget or (host == "api.openalex.org" and self.host_requests.get(host, 0) >= 700) or (host == "api.plos.org" and self.host_requests.get(host,0) >= 90):
                raise SourceError("Conservative request budget exhausted; deferred to next refresh")
            # The shared serial PLOS queue stays below 10/minute, 300/hour,
            # and 7200/day. Every journal and retry shares this host pacing.
            interval = 12.1 if host == "api.plos.org" else 1.0 if host == "api.elifesciences.org" else 0.8
            wait = max(0, interval - (self.clock() - self.last.get(host, -1000)))
            if wait:
                self.sleep(wait)
            self.requests += 1
            self.host_requests[host] = self.host_requests.get(host, 0) + 1
            self.last[host] = self.clock()
            request = urllib.request.Request(url, headers={
                "User-Agent": "NeuroPaperRadar/1.0 (https://github.com/jiumao2/neuro-paper-radar)",
                "Accept": "application/json",
            })
            try:
                with self.opener(request, timeout=35) as response:
                    body = response.read(30_000_001)
                if len(body) > 30_000_000:
                    raise SourceError("Oversized API response rejected")
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise SourceError("Unexpected API response shape")
                result["_retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                return result
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return {"_not_found": True, "_retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
                if error.code not in {429, 500, 502, 503, 504}:
                    raise SourceError(f"Official API returned HTTP {error.code}") from error
                delay = retry_delay(error.headers.get("Retry-After"), attempt)
                # Defer rather than sleeping less than a server's Retry-After.
                if delay > 60 or attempt == 2:
                    raise SourceError(f"Official API HTTP {error.code}; retry deferred") from error
                self.sleep(delay)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as error:
                if attempt == 2:
                    raise SourceError(f"Official API request failed ({type(error).__name__})") from error
                self.sleep(retry_delay(None, attempt))
        raise SourceError("Official API request failed")
