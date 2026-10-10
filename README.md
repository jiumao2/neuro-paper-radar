# NeuroPaper Radar

[中文说明](README.zh-CN.md) · [GNU GPL v3](LICENSE)

**[Open NeuroPaper Radar](https://jiumao2.github.io/neuro-paper-radar/)**

An open, bilingual radar for neuroscience preprints and published papers. Independently implemented, with inspiration from the static ingestion/ranking approach of [biorxiv-top](https://github.com/RobertoDF/biorxiv-top); no code or interface is copied from that project.

The project uses Python ingestion, a TypeScript static frontend, GitHub Actions, and GitHub Pages. Production metadata comes from the official bioRxiv, Crossref, and OpenAlex APIs. Initial published journals are Nature, Nature Neuroscience, Nature Methods, Nature Communications, and Journal of Neuroscience, identified by stable ISSNs. Multidisciplinary journals require recorded neuroscience classification evidence.

## Metrics and publication dates

The intended default is raw accesses descending, with citations (OpenAlex) and newest as alternatives. Missing metrics are distinct from measured zero. No permitted automated per-paper readership source has been established: the initial access column is unavailable and the access view transparently falls back to citations, then newest when no citation measurements exist. Cross-publisher raw access counts, when available, will not be fully comparable. No fabricated counts, publisher metrics scraping, or Altmetric feed is used.

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

## Automation and deployment

GitHub Pages uses **GitHub Actions** as its source. [Verify and deploy](.github/workflows/verify-deploy.yml) checks Python tests, data validity, TypeScript, lint, unit tests, browser flows/accessibility on desktop and mobile, then builds and deploys. An empty bootstrap snapshot is not deployed.

[Refresh official paper data](.github/workflows/refresh.yml) runs at `00:17`, `06:17`, `12:17`, and `18:17` UTC. One schedule handles metadata, daily citations, and weekly repair without redundant schedules. Successful weekly source backfills are remembered separately, so one failing source does not multiply full backfills of successful sources. Manual modes are available in Actions. Refreshes commit only the public snapshot, coverage report, and last-good state, then deploy that snapshot. GitHub may delay or disable inactive repository schedules.

Permissions are granular: ordinary verification reads repository content; only the refresh job writes data; only deploy jobs have `pages: write` and `id-token: write`. Actions are pinned to verified upstream commit SHAs. No paid services, account creation, persistent credentials, or client secrets are required. `build-info.json` records the actual built commit, workflow run, and snapshot timestamp.

Date windows default to **Past 30 days**. Today is a UTC calendar day; past 7/30 days include today and the preceding 6/29 days. Month/year windows use inclusive dates and calendar subtraction with end-of-month/leap-year clamping. Filters are preserved in the URL; the English/Chinese choice persists locally. Original titles and topic names are retained.

See [source policies and limitations](docs/SOURCES.md) for classification, metrics, licensing, and permitted adapter requirements. Contributions must preserve these constraints; project instructions are in [AGENTS.md](AGENTS.md).

The published feed includes publisher-classified `journal-article` records and can contain corrections, commentary, or editorial conversations. It is not restricted to original research articles.
