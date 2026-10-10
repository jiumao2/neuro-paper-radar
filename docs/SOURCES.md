# Sources, rights, and coverage

These policies were checked against official documentation on 2026-10-10. Successful HTTP access alone is not permission to collect or republish content.

| Source | Production use | Rights / constraints |
| --- | --- | --- |
| [bioRxiv API](https://api.biorxiv.org/) | Neuroscience category, authors, versions, v1 dates, related published DOI, individually licensed abstracts | The details API paginates; advance by the actual returned page length. Its usage API contains site-wide totals, not per-paper counts. Preprint identity follows the official category/server, including newer DOI prefixes such as 10.64898. |
| [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | Exact journal ISSNs and publisher-deposited `published-online` dates; bibliographic metadata | Metadata is reusable; abstracts are not blanket licensed and are excluded. Partial dates are omitted rather than invented. Deposit/ingestion dates never replace online dates. |
| [OpenAlex](https://help.openalex.org/api/authentication/) | CC0 topics, keywords, work IDs, raw `cited_by_count` | Basic keyless queries are supported. [OR lookups](https://help.openalex.org/api/filtering/) allow up to 100 values and supported `per_page` is 100. The implementation batches 75 DOIs, with a bounded singleton alias queue. [Keyless budget](https://help.openalex.org/access/example-costs/) is limited; no API key or paid plan is used. |
| Nature article/metrics pages | Disabled | [Robots](https://www.nature.com/robots.txt) disallow metrics paths; [additional terms](https://www.nature.com/info/additional-terms) restrict automated journal access. No alternate endpoint or badge is used to bypass these restrictions. |
| JNeurosci per-paper usage | Disabled | Systematic collection/republication permission not verified. |
| bioRxiv per-paper usage pages | Disabled | No verified per-paper reuse route. Site-wide usage is not assigned to individual papers. |
| Altmetric | Disabled | A key and display/republication authorization are required. Attention is a separate metric from readership. |
| [OpenAIRE Graph](https://graph.openaire.eu/docs/apis/terms/) | Optional future repository-usage adapter; not a launch dependency | API data permits CC-BY reuse with attribution; unauthenticated limit is 60 requests/hour. [Usage semantics](https://graph.openaire.eu/docs/graph-production-workflow/indicators-ingestion/usage-counts/) are participating repository COUNTER downloads and metadata views, not publisher accesses or unique readers. Core recent journal/preprint probes had no usage counts, so this does not solve current coverage. Missing usage remains null. Merged publication dates must never replace primary-source dates. |

## Selection

Journal identities are the exact configured ISSNs in [sources.json](../config/sources.json). Nature Neuroscience and Journal of Neuroscience use their neuroscience journal scope. For Nature, Nature Methods, and Nature Communications, at least one of the top three OpenAlex topics must have field ID `https://openalex.org/fields/28` and score at least 0.35. The evidence and score are retained. Unknown/non-neuroscience classifications are excluded from multidisciplinary lists; relevant papers may be missed. Included records without topics remain explicitly unknown.

Initial/weekly ingestion requests the rolling past calendar year of v1/first-online dates. Regular metadata refreshes overlap the previous eight days to recover indexing delays; weekly repair revisits the whole year, topic classification, versions, and related publication links. Missing initial v1 records are resolved from the official single-DOI endpoint in a bounded queue; unresolved v1 records are omitted and counted. Corrections and other `journal-article` records can be included by the depositing source. No promise of complete publisher inventories is made.

## Raw metric semantics

`accesses` and `citations` are independent nullable integers. Zero is measured zero; null is missing. Each measured value requires a source and UTC observation timestamp. Raw accesses require a documented definition, aggregation/window, and collection/republication permission. Cross-publisher raw values may cover different periods and events and are not fully comparable.

No approved publisher-access feed is configured. Access sorting remains available and prominently falls back to measured citations, then newest if all citations in the current filtered view are missing. Unmeasured values have no rank; measured ties share ranks. No normalized score or weighted composite is computed.

OpenAlex counts describe one work and can merge preprint/publication versions. A preprint and its related published record can appear in their respective tabs, with the same OpenAlex work ID visible. Their citations are never added together. A missing DOI match or failed request does not erase a previous measurement. The measurement timestamp remains the last successful observation, not the refresh attempt time.

## Optional readership imports

`ingest/readership.py` provides permission-aware import validation and a serial rate-limited queue extension point. All current publisher adapters are disabled in configuration. An enabled provider must explicitly record collection/republication permission, an HTTPS permission evidence URL, and a metric definition. Imported cumulative snapshots replace rather than sum counts; windowed metrics need a stated window. The module is an extension point; no provider is automatically activated, and no sample import is published as production data. OpenAIRE repository views/downloads must remain separate fields rather than being silently mapped to publisher accesses.

## Reliability and source rights

Source requests are serial, bounded, and use an honest project user agent. Retry-After is respected: long waits are deferred rather than retried early. Restricted hosts are refused by the metadata client. Source failures retain last-good state and report partial coverage; validation failure leaves the prior public snapshot intact. The initial empty scaffold is never deployed.

Only bioRxiv abstracts marked CC-BY, CC-BY-SA, or CC0 are redistributed, with paper authors, source links, and license attribution. Other abstracts link to the source. The original code license, GPL-3.0-only, does not extend to third-party metadata or literature. No full text or unlicensed publisher abstract is included. The browser uses no third-party analytics, fonts, or runtime API credentials.
