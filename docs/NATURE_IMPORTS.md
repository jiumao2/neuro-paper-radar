# Nature access imports

[中文说明](NATURE_IMPORTS.zh-CN.md)

The deployed module supports **authorized local HTML, CSV, and JSON numerical imports** for Nature, Nature Neuroscience, Nature Methods, and Nature Communications. **Live Nature collection is disabled, and no authorized production export has been supplied.** An installed parser does not establish a readership connection. The app shows actual measured coverage and falls back transparently to citations/newest when access values are missing.

## Verified launch coverage · 2026-10-11

The production snapshot generated at `2026-10-11T09:54:11Z` contains the following included records for the rolling `2025-10-11`–`2026-10-11` publication window. These are verified metadata counts, not claims of complete journal inventories or connected access data.

| Journal | Included papers | Access measurements | First/last included online date |
| --- | ---: | ---: | --- |
| Nature | 222 | 0 | 2025-10-15 / 2026-10-09 |
| Nature Neuroscience | 395 | 0 | 2025-10-13 / 2026-10-08 |
| Nature Methods | 28 | 0 | 2025-11-06 / 2026-10-07 |
| Nature Communications | 736 | 0 | 2025-10-13 / 2026-10-09 |

The four journals total **1,381 papers and zero authorized imported access measurements**. Citation/newest discovery is available. Multidisciplinary journals use recorded OpenAlex neuroscience classification; excluded or unclassified candidates are not counted. Crossref metadata last succeeded around `05:46 UTC`; this later snapshot reused the valid five-hour cache, rather than making redundant requests. Full source timestamps and changing counts remain in the live coverage report. The corpus also retains bioRxiv readership and real eLife/PLOS API measurements.

## Source boundary and code reference

[ScrapeJournal](https://github.com/danmonyak/ScrapeJournal/tree/0d9b84a214b7104b57fb7363791e4caacafdee9c) is MIT-licensed. Its [article parser](https://github.com/danmonyak/ScrapeJournal/blob/0d9b84a214b7104b57fb7363791e4caacafdee9c/src/sitelogic/NatureArticle.py) identifies the ordinary article-page `.c-article-metrics-bar__wrapper`. That bar is separate from `/metrics`; a restriction on `/metrics` alone does not determine the article parser's eligibility. Its [download script](https://github.com/danmonyak/ScrapeJournal/blob/0d9b84a214b7104b57fb7363791e4caacafdee9c/download.py) uses Nature search and skips existing database DOIs, so its collection/update pipeline is not adopted here.

On 2026-10-11, Nature's [robots policy](https://www.nature.com/robots.txt) disallows all pages for `ChatGPT-User` and `GPTBot`, as well as search and metrics routes in its general rules. [Additional terms](https://www.nature.com/info/additional-terms) restrict automated content access/reuse. No permitted live collection and public numerical redistribution route has been verified for this project. No Nature search, article, metrics, alternate endpoint, proxy, or disguised identity is used by the importer. An API key, paid service, new credentials, or contact with a vendor/supervisor is not required by this module.

Our standard-library parser and import pipeline are independently implemented; no ScrapeJournal code is copied. The project remains GPL-3.0-only. The reference's [MIT license](https://github.com/danmonyak/ScrapeJournal/blob/0d9b84a214b7104b57fb7363791e4caacafdee9c/LICENSE.txt) covers its code, not Nature content or data rights.

## Required authorization

An operator must verify rights to **both obtain the specific input and publicly redistribute its numerical facts**, then supply a separate local authorization JSON. The declaration records existing rights; it does not grant them or automatically verify a publisher contract. General Nature terms, a subscription, successful HTTP access, an upstream code license, or a robots file do not establish numerical republication permission.

The following is a **nonfunctional schema illustration**, not permission or production data. Replace the placeholders and change the two booleans only when the declared rights have actually been verified. Keep private permission documents, credentials, raw HTML, and input exports outside version control, for example under the ignored `scratch/` directory. Only public-safe references and numerical facts persist.

```json
{
  "permission_url": "https://<public-permission-or-license-reference>",
  "permission_basis": "<specific verified numerical collection and public redistribution rights>",
  "license": "LicenseRef-ExplicitPermission",
  "verified_at": "<ISO timestamp with UTC offset>",
  "journal_ids": ["nature-neuroscience"],
  "collection_allowed": false,
  "redistribution_allowed": false
}
```

Supported numerical license identifiers are `CC0-1.0`, `CC-BY-4.0`, and `LicenseRef-ExplicitPermission`. Permission scope must use exact supported journal IDs. Evidence URLs must be public HTTPS links without credentials or signed query parameters; a general Nature homepage, robots file, or restrictive terms page is rejected as permission evidence.

## Import numerical CSV or JSON

CSV columns are `doi,journal_id,accesses,observed_at,source_url,source_updated_at,source_label`. The final three are optional: the matching ordinary article URL can be derived from the DOI; an unknown publisher metric timestamp remains unknown; the default source label is `Accesses`. `Views` is also supported. Citations/Altmetric are excluded and OpenAlex citations remain unchanged.

JSON accepts an array of the same record fields, or `{"schema_version":1,"records":[...]}`. Titles, authors, abstracts, full text, arbitrary extra fields, and credentials are not accepted as imported records. **Only DOIs already present in official publisher metadata, with matching exact journal ISSNs and authorization scope, can be imported.** Existing neuroscience classification/date rules still determine inclusion in the visible corpus.

```sh
python -m ingest.nature_import --file scratch/authorized-counts.csv \
  --authorization scratch/verified-numerical-permission.json
```

`observed_at` must be the actual source capture time with a UTC offset. `source_updated_at`, when supplied by the source, must not exceed that observation. Neither a file modification time nor import time is substituted for either source timestamp. Future timestamps are rejected.

## Import authorized saved article HTML

HTML must identify the same DOI in citation/canonical metadata; the ordinary article metrics bar is parsed when present. Supply its actual capture timestamp and the verified journal ID:

```sh
python -m ingest.nature_import --file scratch/authorized-article.html \
  --authorization scratch/verified-numerical-permission.json \
  --doi '<existing verified DOI>' --journal-id nature-neuroscience \
  --observed-at '<actual source capture timestamp with UTC offset>'
```

No URL is fetched. HTML input is capped at 5 MB. Only DOI identity and the access/view counter are extracted; article text, abstracts, author lists, and other metrics are discarded. Missing bars/counters produce missing observations without crashing. Conflicting DOI identities, malformed counters, conflicting repeated bars, and unclosed metric bars reject the batch. Search/metrics URLs cannot be assigned as the counter's source.

## Precision, updates, and publication

Exact `0` is measured zero. Empty/absent counts, `—`, and `N/A` are missing. Displays such as `1.2k`, `2.3M`, or `0k` retain the original source display and an explicit approximation flag. They expand to 1,200, 2,300,000, or 0 for ordering, while the UI marks them with `≈` and a publisher-rounded label. No unverified precision, range, readership population, or time cutoff is inferred. Ordinary compact UI formatting of an exact count remains distinct from source rounding.

Newer observations replace existing DOI measurements, including legitimate decreases or zero; values are never summed. Missing and older observations retain the last-good value, source capture time, and permission evidence. Conflicting values at the same timestamp reject the batch. The entire batch and resulting snapshot are validated before writes; malformed data leaves all last-good files unchanged. Corrected inputs can then be imported normally.

The importer updates only sanitized state in `data/state.json.gz`, `public/data/papers.json`, and `data/coverage.json`. Provenance includes the original source URL/capture time, optional publisher timestamp, import time, raw display/precision, format, input fingerprint, and public permission/license reference. A SHA-256 fingerprint supports provenance; it is not permission evidence. Raw HTML and permission documents are not stored in the public snapshot.

After validating, commit these three output files through the repository's normal authorized publication process. A regular commit triggers verification and Pages deployment; do not add the refresh workflow's `[skip ci]` marker to a manual import publication. Subsequent scheduled refreshes retain and revalidate imported observations without making any Nature requests. Browser snapshot validation rejects malformed Nature provenance/precision and retains its last-good cached content.
