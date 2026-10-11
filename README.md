# NeuroPaper Radar

[中文说明](README.zh-CN.md) · [GNU GPL v3](LICENSE)

**[Open NeuroPaper Radar](https://jiumao2.github.io/neuro-paper-radar/)**

An open, bilingual radar for neuroscience preprints and published papers. Independently implemented, with inspiration from the static ingestion/ranking approach of [biorxiv-top](https://github.com/RobertoDF/biorxiv-top); no code or interface is copied from that project.

The project uses Python ingestion, a TypeScript static frontend, GitHub Actions, and GitHub Pages. Production metadata comes from the official bioRxiv, Crossref, OpenAlex, and PLOS APIs. Published journals are Nature, Nature Neuroscience, Nature Methods, Nature Communications, Journal of Neuroscience, eLife, PLOS Biology, PLOS Computational Biology, and PLOS ONE, identified by stable ISSNs. Multidisciplinary journals require recorded neuroscience classification evidence.

## Metrics and publication dates

The default preprint view ranks real raw readership from the public [biorxiv-top numerical snapshot](https://github.com/RobertoDF/biorxiv-top/blob/data/usage.json): available monthly full-text views plus PDF downloads, with a pinned source commit and collection/retrieval timestamps. Only DOI-keyed numerical facts are reused; titles, authors, and publication dates come from our official metadata ingestion. Its recent cohort and reported months are partial, current-month counts are incomplete, and lifetime/all-version completeness is not verified. These are events, not unique readers. Publication-date filters select papers, not readership event dates.

Preprints with a known related published DOI are hidden by default; a toggle includes them. A missing publication link does not prove a paper is unpublished. Citations (OpenAlex) and newest remain available. Missing metrics differ from source-reported zero and follow measured values without a rank. For a filtered view with no readership measurements, the app explicitly falls back to citations, then newest. Published readership comes from permitted official PLOS and eLife APIs. The four Nature journals support authorized offline imports, but currently have **zero imported production measurements** and live fetching stays disabled. Journal of Neuroscience readership remains unavailable. No restricted publisher scraping or Altmetric feed is used. Cross-source raw metrics are not fully comparable.

The [Nature import module](docs/NATURE_IMPORTS.md) accepts permission-verified local HTML, CSV, or JSON for existing DOI records, without making publisher requests. It preserves rounded `k`/`m` displays as approximate counts, source/observation/import timestamps, and permission evidence; invalid imports retain the last-good snapshot. [ScrapeJournal](https://github.com/danmonyak/ScrapeJournal) helped identify the ordinary article-page metrics bar; our parser is independently implemented. Its MIT code license does not authorize collection or republication of Nature data.

PLOS reports source-defined all-time total views as the primary metric, and last-30-days views separately. Every PLOS row carries “Data Provided by PLOS.” Source-reported zero can mean an index awaiting update; the index timestamp is not a guaranteed metric cutoff. PLOS requests share a serial 12.1-second queue, at most 100 rows per request, within documented minute/hour/day limits.

eLife uses documented cumulative `totalValue` page views, never a first-page sum. Downloads remain separate. Counts cover all eLife versions, including reviewed preprints before formal publication. Only entries with verified `status=vor`, `stage=published` in the official version history enter Published; their first VOR date and prior reviewed-preprint date are separate. Version DOI suffixes canonicalize to one article ID. A bounded cache/queue retains last-good counts and reports deferred work.

Preprints use the first v1 posting date; published papers use a verified first online publication date, never deposit/ingestion dates. Revision histories and related published DOIs are retained. Topic classification is automatic and uncertainty is visible.

## License and source rights

Original project code is licensed **GPL-3.0-only**; see the canonical [GNU General Public License version 3](LICENSE). This license does not relicense third-party papers or metadata. OpenAlex metadata is CC0. Crossref metadata is reusable, but its abstracts do not have a blanket reuse license. bioRxiv abstracts are displayed only with a recorded license allowing redistribution; otherwise the app links to the original source. Each record retains provenance. Restricted publisher content and unverified readership endpoints are excluded.

## Run and check

Requires Node.js 24 and Python 3.12+, with no Python dependencies or API credentials.

```sh
npm ci
npm run dev
python -m unittest discover -s tests -v
python -m ingest.validate
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

For an installed system Chromium, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium`. Browser fixtures are clearly marked test data and never enter the production snapshot.

```sh
python -m ingest.refresh --mode backfill  # initial rolling calendar year
python -m ingest.refresh --mode auto      # metadata + only-due citation/repair work
```

The public snapshot is `public/data/papers.json`; the exact coverage report is [data/coverage.json](data/coverage.json) after ingestion. Compressed, source-specific last-good state is `data/state.json.gz`. Invalid refreshes do not replace the public snapshot; API failures retain source records and report failures. Browser IndexedDB retains a last-good snapshot for a failed subsequent fetch.

The shared API client stops new requests after a 30-minute time budget, including rate-limit waits and retries. Successful partial records are validated and persisted before the 40-minute job deadline; deferred work and stale sources remain explicit and resume in later refreshes.

Recent metadata, eLife metrics, and negative eLife histories are cached for five hours. This deduplicates rapid reruns while leaving collection time and scheduling slack before the next six-hour scheduled refresh.

## Automation and deployment

GitHub Pages uses **GitHub Actions** as its source. [Verify and deploy](.github/workflows/verify-deploy.yml) checks Python tests, data validity, TypeScript, lint, unit tests, browser flows/accessibility on desktop and mobile, then builds and deploys. An empty bootstrap snapshot is not deployed.

[Refresh official paper data](.github/workflows/refresh.yml) runs at `00:17`, `06:17`, `12:17`, and `18:17` UTC. One schedule handles metadata, daily citations, and weekly repair without redundant schedules. Successful weekly source backfills are remembered separately, so one failing source does not multiply full backfills of successful sources. Manual modes are available in Actions. Refreshes commit only the public snapshot, coverage report, and last-good state, then deploy that snapshot. GitHub may delay or disable inactive repository schedules.

Permissions are granular: ordinary verification reads repository content; only the refresh job writes data; only deploy jobs have `pages: write` and `id-token: write`. Actions are pinned to verified upstream commit SHAs. No paid services, account creation, persistent credentials, or client secrets are required. `build-info.json` records the actual built commit, workflow run, and snapshot timestamp.

Date windows default to **Past 30 days**. Today is a UTC calendar day; past 7/30 days include today and the preceding 6/29 days. Month/year windows use inclusive dates and calendar subtraction with end-of-month/leap-year clamping. Filters are preserved in the URL; the English/Chinese choice persists locally. Original titles and topic names are retained.

See [source policies and limitations](docs/SOURCES.md) and [authorized Nature imports](docs/NATURE_IMPORTS.md) for classification, metrics, licensing, and adapter requirements. Contributions must preserve these constraints; project instructions are in [AGENTS.md](AGENTS.md).

The published feed includes publisher-classified `journal-article` records and can contain corrections, commentary, or editorial conversations. It is not restricted to original research articles.

[Official provider contracts](.github/workflows/provider-contract.yml) perform four bounded read-only API checks after provider code changes or manual dispatch, with no independent schedule. Production refresh live QA requires actual readership measurements for eLife and the three PLOS journals, and verifies the Nature module's honest coverage notice.
