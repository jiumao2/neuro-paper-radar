"""GPL-3.0-only. Offline numeric parser; never fetches a Nature URL.

The article-bar selector was identified in ScrapeJournal (MIT). This parser is
independently implemented with the standard library; no upstream code is copied.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from ingest.model import doi

NATURE_JOURNALS = ("nature", "nature-neuroscience", "nature-methods", "nature-communications")
MAX_SAFE_COUNT = 2**53 - 1
MAX_HTML_BYTES = 5_000_000
_NUMBER = re.compile(r"^(\d+|\d{1,3}(?:,\d{3})+|\d{1,3}(?: \d{3})+)(?:\.(\d+))?([km])?$", re.I)
_SUFFIX = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.I)


def nature_doi(value):
    identifier = doi(value)
    if not identifier or not identifier.startswith("10.1038/") or not _SUFFIX.fullmatch(identifier[8:]):
        raise ValueError("Nature import requires a supported 10.1038 article DOI")
    return identifier


def article_url(identifier):
    return "https://www.nature.com/articles/" + nature_doi(identifier)[8:]


def article_doi(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"nature.com", "www.nature.com"} or parsed.username or parsed.password or parsed.port:
            raise ValueError("Nature source URL must be a public HTTPS article URL")
        path = unquote(parsed.path).rstrip("/")
        match = re.fullmatch(r"/articles/([a-z0-9][a-z0-9._-]*)", path, re.I)
        if not match:
            raise ValueError("Only ordinary Nature article URLs are supported; search and metrics routes are excluded")
        return nature_doi("10.1038/" + match[1])
    except (TypeError, AttributeError) as error:
        raise ValueError("Invalid Nature source URL") from error


def parse_count(value):
    """Preserve a rounded publisher display; its scaled value remains approximate."""
    if value is None:
        return {"value": None, "display_value": None, "approximate": False}
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Nature count must be an integer, numeric display, or missing")
    display = re.sub(r"\s+", " ", str(value)).strip()
    if display.casefold() in {"", "—", "–", "-", "n/a", "na", "not available"}:
        return {"value": None, "display_value": None, "approximate": False}
    if len(display) > 80:
        raise ValueError("Nature numeric display is too long")
    match = _NUMBER.fullmatch(display)
    if not match or (match[2] and not match[3]):
        raise ValueError("Malformed Nature count; no inferred or fabricated value")
    number = match[1].replace(",", "").replace(" ", "") + ("." + match[2] if match[2] else "")
    try:
        with localcontext() as context:
            context.prec = len(number)+8
            scaled = Decimal(number) * {None: 1, "k": 1000, "m": 1_000_000}[match[3].lower() if match[3] else None]
            if scaled != scaled.to_integral_value() or not 0 <= scaled <= MAX_SAFE_COUNT:
                raise ValueError("Nature count must scale to a safe nonnegative integer")
    except InvalidOperation as error:
        raise ValueError("Malformed Nature numeric display") from error
    return {"value": int(scaled), "display_value": display, "approximate": bool(match[3])}


class ArticleBar(HTMLParser):
    """Read only DOI identity and the ordinary article's access/view count."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.identifiers = set()
        self.count = None
        self.counts = []
        self.bar_seen = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").casefold()
            content = attrs.get("content", "")
            if name in {"citation_doi", "dc.identifier", "dc.identifier.doi"} and (name != "dc.identifier" or doi(content)):
                self.identifiers.add(nature_doi(content))
            elif name == "og:url":
                self.identifiers.add(article_doi(content))
        elif tag == "link" and "canonical" in (attrs.get("rel") or "").casefold().split():
            self.identifiers.add(article_doi(attrs.get("href", "")))
        classes = (attrs.get("class") or "").split()
        bar = "c-article-metrics-bar__wrapper" in classes
        inside = bar or any(b for _, b in self.stack)
        if bar:
            self.bar_seen = True
        if inside and "c-article-metrics-bar__count" in classes:
            if self.count:
                raise ValueError("Nested metric counts are ambiguous")
            self.count = {"tag": tag, "depth": len(self.stack), "text": []}
        if tag not in self.VOID:
            self.stack.append((tag, bar))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.count and not any(t in {"script", "style"} for t, _ in self.stack):
            self.count["text"].append(data)

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack)-1, -1, -1) if self.stack[i][0] == tag), None)
        if index is None:
            return
        if self.count and index <= self.count["depth"]:
            if tag != self.count["tag"] or index != self.count["depth"]:
                raise ValueError("Unclosed Nature metric count")
            text = re.sub(r"\s+", " ", "".join(self.count["text"])).strip()
            primary = re.fullmatch(r"(.+?)\s*(Accesses|Views)", text, re.I)
            if primary:
                self.counts.append({**parse_count(primary[1].strip()), "source_label": primary[2].title()})
            elif re.search(r"\b(?:accesses|views)\b", text, re.I):
                raise ValueError("Malformed Nature access counter")
            self.count = None
        del self.stack[index:]


def parse_html(body, expected_doi=None, source_url=None):
    if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("Nature HTML must be a bounded local text file")
    parser = ArticleBar()
    parser.feed(body)
    parser.close()
    if parser.count or any(bar for _, bar in parser.stack):
        raise ValueError("Unclosed Nature article metric bar")
    if len(parser.identifiers) != 1:
        raise ValueError("Nature HTML must identify exactly one article through DOI/canonical metadata")
    identifier = next(iter(parser.identifiers))
    if expected_doi and nature_doi(expected_doi) != identifier:
        raise ValueError("Nature HTML DOI does not match the requested article")
    if source_url and article_doi(source_url) != identifier:
        raise ValueError("Nature HTML source URL and DOI disagree")
    measured = [r for r in parser.counts if r["value"] is not None]
    if len({(r["value"], r["approximate"], r["source_label"]) for r in measured}) > 1:
        raise ValueError("Conflicting Nature counters; no value selected")
    reading = measured[0] if measured else {"value": None, "display_value": None, "approximate": False, "source_label": "Accesses"}
    return {"doi": identifier, "source_url": article_url(identifier), **reading,
            "missing_reason": None if measured else "access counter absent or missing"}
