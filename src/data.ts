import type { Snapshot } from './types';

export function validSnapshot(value: unknown): value is Snapshot {
  const object = (v: unknown): v is Record<string,unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
  const text = (v: unknown): v is string => typeof v === 'string';
  const count = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
  const texts = (v: unknown): v is string[] => Array.isArray(v) && v.every(text);
  const timestamp = (v: unknown) => text(v) && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
  const day = (v: unknown) => text(v) && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0,10) === v;
  const nullable = (v: unknown, test: (v:unknown)=>boolean) => v === null || test(v);
  const doi = (v: unknown): v is string => text(v) && /^10\.\d{4,9}\/[^\s<>"#?]+$/i.test(v);
  const url = (v: unknown) => { try { if(!text(v)) return false;const u=new URL(v);return u.protocol==='https:' && !!u.hostname && !u.username && !u.password; } catch {return false;} };
  const optional = (v:Record<string,unknown>,key:string,test:(v:unknown)=>boolean) => v[key] === undefined || v[key] === null || test(v[key]);
  const commit = (v:unknown) => text(v) && /^[a-f0-9]{40}$/.test(v);
  const natureIds=['nature','nature-neuroscience','nature-methods','nature-communications'];
  const naturePrecision = (v:Record<string,unknown>) => {
    if(!text(v.display_value) || v.display_value.length>80 || typeof v.approximate!=='boolean')return false;
    const m=/^(\d+|\d{1,3}(?:,\d{3})+|\d{1,3}(?: \d{3})+)(?:\.(\d+))?([km])?$/i.exec(v.display_value);
    if(!m || (!!m[2]&&!m[3]) || v.approximate!==!!m[3])return false;
    const numerator=BigInt(m[1].replace(/[, ]/g,'')+(m[2]||''))*BigInt(m[3]?.toLowerCase()==='m'?1000000:m[3]?1000:1);
    const denominator=10n**BigInt(m[2]?.length||0);
    return numerator%denominator===0n && Number(numerator/denominator)===v.value;
  };
  const metricBase = (v: unknown) => object(v) && nullable(v.value,count) && nullable(v.source,text) && nullable(v.observed_at,timestamp)
    && (v.value === null || (text(v.source) && !!v.source && timestamp(v.observed_at)))
    && (v.work_id === undefined || (text(v.work_id) && /^https:\/\/openalex\.org\/W\d+$/.test(v.work_id)));
  const metric = (v:unknown) => object(v) && metricBase(v)
    && ['scope','definition','provider','aggregation','attribution','version_scope','zero_caveat','display_value','source_label','permission_basis','permission_license','input_format'].every(k=>optional(v,k,text))
    && ['permission_url','source_url'].every(k=>optional(v,k,url)) && optional(v,'source_commit',commit)
    && ['fulltext','pdf'].every(k=>optional(v,k,count)) && optional(v,'upstream_fetched_date',day)
    && ['upstream_updated_at','source_indexed_at'].every(k=>optional(v,k,timestamp))
    && optional(v,'approximate',a=>typeof a==='boolean') && (v.approximate!==true || text(v.display_value))
    && optional(v,'reported_months',months=>Array.isArray(months) && months.every(m=>text(m) && /^\d{4}-\d{2}$/.test(m) && day(m+'-01')))
    && optional(v,'recent_30_days',metricBase);
  const natureMetric = (v:Record<string,unknown>,identifier:string,journal:string) => v.provider!=='nature-offline-import' || (
    natureIds.includes(journal) && identifier.startsWith('10.1038/') && v.source_url==='https://www.nature.com/articles/'+identifier.slice(8)
    && v.aggregation==='cumulative' && ['Accesses','Views'].includes(String(v.source_label)) && naturePrecision(v)
    && timestamp(v.imported_at) && optional(v,'source_updated_at',timestamp) && timestamp(v.permission_verified_at)
    && text(v.import_fingerprint) && /^[a-f0-9]{64}$/.test(v.import_fingerprint) && ['html','csv','json'].includes(String(v.input_format))
    && url(v.permission_url) && text(v.permission_basis) && v.permission_basis.trim().length>=20
    && ['CC0-1.0','CC-BY-4.0','LicenseRef-ExplicitPermission'].includes(String(v.permission_license))
    && texts(v.permission_journal_ids) && v.permission_journal_ids.includes(journal) && v.permission_journal_ids.every(j=>natureIds.includes(j))
    && v.collection_allowed===true && v.redistribution_allowed===true);
  const source = (v:unknown) => object(v) && text(v.id) && ['ok','failed','partial','pending'].includes(String(v.status))
    && timestamp(v.checked_at) && nullable(v.last_success,timestamp) && count(v.rows) && day(v.requested_start) && day(v.requested_end) && texts(v.errors)
    && optional(v,'source_commit',commit) && optional(v,'source_url',url) && optional(v,'upstream_updated_at',timestamp);
  if(!object(value)) return false;
  const d = value;
  if(d.schema_version !== 1 || !timestamp(d.generated_at) || !Array.isArray(d.papers) || !object(d.coverage) || !Array.isArray(d.sources) || !object(d.schedule) || !object(d.readership)) return false;
  const c=d.coverage,s=d.schedule;
  if(!['total','preprints','published','accesses','citations','topics','abstracts'].every(k=>count(c[k])) || c.total !== d.papers.length
    || (c.preprints as number)+(c.published as number)!==c.total || !day(c.requested_start) || !day(c.requested_end)
    || !nullable(c.oldest,day) || !nullable(c.newest,day) || !object(c.excluded) || !Object.values(c.excluded).every(count)
    || !Array.isArray(c.by_journal) || !c.by_journal.every(j=>object(j) && text(j.id) && text(j.name) && count(j.count) && count(j.candidates) && nullable(j.oldest,day) && nullable(j.newest,day))) return false;
  if(!count(s.metadata_hours) || !text(s.citations) || !text(s.repair) || !nullable(s.last_citations,timestamp) || !nullable(s.last_repair,timestamp)
    || !text(d.readership.status) || !text(d.readership.reason) || d.readership.measured !== c.accesses) return false;
  if(!d.sources.every(source) || !optional(d.readership,'source',source)) return false;
  if(!optional(d.readership,'nature',n=>object(n) && n.module==='offline-import' && n.live_fetch_enabled===false
    && ['partial','awaiting-authorized-data'].includes(String(n.status)) && count(n.measured) && count(n.total) && count(n.approximate)
    && n.measured<=n.total && n.approximate<=n.measured && nullable(n.last_import,timestamp) && texts(n.errors)))return false;
  const ids = new Set<string>();
  return d.papers.every(p=>{
    if(!object(p) || !doi(p.doi) || p.id!==p.doi || ids.has(p.id as string) || !text(p.title) || !p.title || !['preprint','published'].includes(String(p.kind))
      || !texts(p.authors) || !day(p.date) || !text(p.date_source) || !text(p.journal_id) || !text(p.journal) || !timestamp(p.metadata_observed_at)
      || p.article_url!=='https://doi.org/'+p.doi || !texts(p.keywords) || !nullable(p.related_doi,doi) || !nullable(p.abstract,text) || !nullable(p.abstract_license,text)
      || (p.abstract && !['CC0-1.0','CC-BY-4.0','CC-BY-SA-4.0'].includes(String(p.abstract_license))) || !metric(p.accesses) || !metric(p.citations)
      || !natureMetric(p.accesses as Record<string,unknown>,p.doi,p.journal_id)
      || !optional(p,'downloads',metric) || !optional(p,'vor_date',day) || !optional(p,'reviewed_preprint_date',day)
      || !optional(p,'publication_history',rows=>Array.isArray(rows) && rows.every(v=>object(v) && ['vor','reviewed-preprint','preprint'].includes(String(v.status)) && doi(v.doi) && day(v.date)))
      || !Array.isArray(p.versions) || !p.versions.every(v=>object(v) && count(v.version) && v.version>0 && day(v.date))
      || (p.kind==='preprint' && !p.versions.some(v=>v.version===1 && v.date===p.date))
      || !Array.isArray(p.topics) || !p.topics.every(topic=>object(topic) && text(topic.id) && /^https:\/\/openalex\.org\/T\d+$/.test(topic.id) && text(topic.name)
        && typeof topic.score==='number' && Number.isFinite(topic.score) && topic.score>=0 && topic.score<=1 && nullable(topic.field_id,text) && text(topic.source) && typeof topic.automatic==='boolean')
      || !object(p.classification) || !text(p.classification.method) || !(text(p.classification.evidence)||texts(p.classification.evidence)) || typeof p.classification.automatic!=='boolean'
      || !Array.isArray(p.provenance) || !p.provenance.every(source=>object(source) && text(source.source) && url(source.url) && timestamp(source.observed_at) && text(source.license))) return false;
    ids.add(p.id as string);return true;
  });
}

async function cache(mode: 'read' | 'write', snapshot?: Snapshot): Promise<Snapshot | null> {
  try {
    const db = await new Promise<IDBDatabase>((resolve,reject) => {
      const request = indexedDB.open('neuro-paper-radar',1);
      request.onupgradeneeded = () => request.result.createObjectStore('snapshots');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return await new Promise<Snapshot | null>((resolve,reject) => {
      const tx = db.transaction('snapshots', mode === 'write' ? 'readwrite' : 'readonly');
      const store = tx.objectStore('snapshots');
      const request = mode === 'write' ? store.put(snapshot,'last-good') : store.get('last-good');
      let result: Snapshot | null = null;
      request.onsuccess = () => { result = mode === 'read' && validSnapshot(request.result) ? request.result : snapshot || null; };
      tx.oncomplete = () => { db.close(); resolve(result); };
      tx.onerror = () => { db.close(); reject(tx.error); };
      tx.onabort = () => { db.close(); reject(tx.error); };
    });
  } catch { return null; }
}

export async function loadSnapshot(previous: Snapshot | null = null): Promise<{ data: Snapshot | null; cached: boolean }> {
  try {
    const response = await fetch(import.meta.env.BASE_URL + 'data/papers.json', { cache:'no-cache', signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error('Data response failed');
    const data: unknown = await response.json();
    if (!validSnapshot(data)) throw new Error('Invalid data snapshot');
    await cache('write',data);
    return { data, cached:false };
  } catch {
    return { data: previous || await cache('read'), cached:true };
  }
}
