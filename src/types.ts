export type Locale = 'en' | 'zh';
export type Kind = 'preprint' | 'published';
export type Sort = 'accesses' | 'citations' | 'newest';
export type WindowKey = 'today' | '7d' | '30d' | '3m' | '6m' | '1y';
export interface Metric {
  value: number | null;
  observed_at: string | null;
  source: string | null;
  work_id?: string;
  scope?: string;
  definition?: string;
  permission_url?: string;
  fulltext?: number; pdf?: number; upstream_fetched_date?: string | null; upstream_updated_at?: string;
  source_commit?: string; source_url?: string; reported_months?: string[];
  provider?:string; attribution?:string; recent_30_days?:Metric; source_indexed_at?:string|null;
  approximate?:boolean; display_value?:string; aggregation?:string; source_label?:string;
  imported_at?:string; source_updated_at?:string|null; input_format?:'html'|'csv'|'json'; import_fingerprint?:string;
  permission_basis?:string; permission_license?:string; permission_verified_at?:string; permission_journal_ids?:string[];
  collection_allowed?:boolean; redistribution_allowed?:boolean;
}
export interface Topic { id: string; name: string; score: number; field_id: string | null; source: string; automatic: boolean }
export interface Paper {
  id: string; doi: string; kind: Kind; title: string; authors: string[]; date: string;
  date_source: string; journal_id: string; journal: string; article_url: string;
  metadata_observed_at: string; topics: Topic[]; keywords: string[];
  versions: { version: number; date: string }[]; updated_date?: string; related_doi: string | null;
  abstract: string | null; abstract_license: string | null; accesses: Metric; citations: Metric;
  downloads?:Metric; vor_date?:string|null; reviewed_preprint_date?:string|null;
  publication_history?:{status:string;doi:string;date:string}[];
  provenance: { source: string; url: string; observed_at: string; license: string }[];
  classification: { method: string; evidence: string | string[]; automatic: boolean; warning?: string };
}
export interface JournalCoverage { id: string; name: string; count: number; candidates: number; measured_accesses?:number; oldest: string | null; newest: string | null }
export interface SourceStatus { id: string; status: string; checked_at: string; last_success: string | null; rows: number; requested_start: string; requested_end: string; errors: string[] }
export interface Snapshot {
  schema_version: 1; generated_at: string; papers: Paper[];
  coverage: { total: number; preprints: number; published: number; accesses: number; citations: number; topics: number; abstracts: number; requested_start: string; requested_end: string; oldest: string | null; newest: string | null; by_journal: JournalCoverage[]; excluded: Record<string, number> };
  sources: SourceStatus[];
  readership: { status: string; measured: number; reason: string; source?: SourceStatus & { source_url?:string;source_commit?:string;upstream_updated_at?:string };
    nature?:{module:'offline-import';live_fetch_enabled:false;status:'partial'|'awaiting-authorized-data';measured:number;total:number;approximate:number;last_import:string|null;errors:string[]} };
  schedule: { metadata_hours: number; citations: string; repair: string; last_citations: string | null; last_repair: string | null };
}
export interface Filters { kind: Kind; window: WindowKey; sort: Sort; journal: string; topic: string; query: string; hidePublished: boolean }
