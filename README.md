# NeuroPaper Radar

[中文说明](README.zh-CN.md) · [GNU GPL v3](LICENSE)

An open, bilingual radar for neuroscience preprints and published papers. Independently implemented, with inspiration from the static ingestion/ranking approach of [biorxiv-top](https://github.com/RobertoDF/biorxiv-top); no code or interface is copied from that project.

The project uses Python ingestion, a TypeScript static frontend, GitHub Actions, and GitHub Pages. Production metadata comes from the official bioRxiv, Crossref, and OpenAlex APIs. Initial published journals are Nature, Nature Neuroscience, Nature Methods, Nature Communications, and Journal of Neuroscience, identified by stable ISSNs. Multidisciplinary journals require recorded neuroscience classification evidence.

## Metrics and publication dates

The intended default is raw accesses descending, with citations (OpenAlex) and newest as alternatives. Missing metrics are distinct from measured zero. No permitted automated per-paper readership source has been established: the initial access column is unavailable and the access view transparently falls back to citations, then newest when no citation measurements exist. Cross-publisher raw access counts, when available, will not be fully comparable. No fabricated counts, publisher metrics scraping, or Altmetric feed is used.

Preprints use the first v1 posting date; published papers use a verified first online publication date, never deposit/ingestion dates. Revision histories and related published DOIs are retained. Topic classification is automatic and uncertainty is visible.

## License and source rights

Original project code is licensed **GPL-3.0-only**; see the canonical [GNU General Public License version 3](LICENSE). This license does not relicense third-party papers or metadata. OpenAlex metadata is CC0. Crossref metadata is reusable, but its abstracts do not have a blanket reuse license. bioRxiv abstracts are displayed only with a recorded license allowing redistribution; otherwise the app links to the original source. Each record retains provenance. Restricted publisher content and unverified readership endpoints are excluded.

Implementation, source documentation, checks, coverage reports, and deployment instructions will be maintained here as the application is built.
