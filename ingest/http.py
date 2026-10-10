"""Small, bounded official-API client. No proxy, identity, or credential tricks."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ALLOWED_HOSTS = {"api.biorxiv.org", "api.crossref.org", "api.openalex.org"}


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
        host = parsed.hostname
        for attempt in range(3):
            if self.requests >= self.budget or (host == "api.openalex.org" and self.host_requests.get(host, 0) >= 700):
                raise SourceError("Conservative request budget exhausted; deferred to next refresh")
            wait = max(0, 0.8 - (self.clock() - self.last.get(host, -1000)))
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
                return result
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return {"_not_found": True}
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
