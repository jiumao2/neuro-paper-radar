import type { Filters, Paper, Sort, WindowKey } from './types';

export const defaults: Filters = { kind: 'preprint', window: '30d', sort: 'accesses', journal: 'all', topic: 'all', query: '', hidePublished:true };
export const journalIds = ['nature','nature-neuroscience','nature-methods','nature-communications','journal-of-neuroscience'];
export const windows: WindowKey[] = ['today','7d','30d','3m','6m','1y'];
export const sorts: Sort[] = ['accesses','citations','newest'];

export function calendarSubtract(date: Date, months: number): Date {
  const year = date.getUTCFullYear(), month = date.getUTCMonth() - months;
  const first = new Date(Date.UTC(year, month, 1));
  const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
  return new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), Math.min(date.getUTCDate(), last)));
}

export function dateWindow(key: WindowKey, now = new Date()): { start: string; end: string } {
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  let start = today;
  if (key === '7d' || key === '30d') start = new Date(today.getTime() - (key === '7d' ? 6 : 29) * 86400000);
  if (key === '3m' || key === '6m' || key === '1y') start = calendarSubtract(today, key === '3m' ? 3 : key === '6m' ? 6 : 12);
  return { start: start.toISOString().slice(0, 10), end: today.toISOString().slice(0, 10) };
}

export function normalizeSearch(value: string): string {
  return value.normalize('NFKD').replace(/\p{M}/gu, '').toLocaleLowerCase();
}

export function filtered(papers: Paper[], filters: Filters, now = new Date()): Paper[] {
  const range = dateWindow(filters.window, now);
  const words = normalizeSearch(filters.query.trim()).split(/\s+/).filter(Boolean);
  return papers.filter(p => p.kind === filters.kind && p.date >= range.start && p.date <= range.end
    && (p.kind !== 'preprint' || !filters.hidePublished || !p.related_doi)
    && (filters.kind === 'preprint' || filters.journal === 'all' || p.journal_id === filters.journal)
    && (filters.topic === 'all' || (filters.topic === 'unknown' ? !p.topics.length : p.topics.some(t => t.id === filters.topic)))
    && words.every(word => normalizeSearch([p.title, ...p.authors, ...p.keywords, ...p.topics.map(t => t.name)].join(' ')).includes(word)));
}

export function resolvedSort(papers: Paper[], requested: Sort): Sort {
  if (requested === 'accesses' && !papers.some(p => p.accesses.value !== null)) return papers.some(p => p.citations.value !== null) ? 'citations' : 'newest';
  return requested;
}

export function sortPapers(papers: Paper[], by: Sort): Paper[] {
  return [...papers].sort((a,b) => {
    if (by !== 'newest') {
      const av = a[by].value, bv = b[by].value;
      if (av === null && bv !== null) return 1;
      if (av !== null && bv === null) return -1;
      if (av !== null && bv !== null && av !== bv) return bv - av;
    }
    return b.date.localeCompare(a.date) || a.id.localeCompare(b.id);
  });
}

export function ranks(papers: Paper[], by: Sort): (number | null)[] {
  let previous: number | null = null, rank: number | null = null;
  return papers.map((p,i) => {
    const value = by === 'newest' ? null : p[by].value;
    if (value === null) return null;
    if (value !== previous) rank = i + 1;
    previous = value;
    return rank;
  });
}

export function readFilters(search: string): Filters {
  const params = new URLSearchParams(search), result = { ...defaults };
  if (params.get('tab') === 'published') result.kind = 'published';
  const windowKey = params.get('window') as WindowKey;
  if (windows.includes(windowKey)) result.window = windowKey;
  const sort = params.get('sort') as Sort;
  if (sorts.includes(sort)) result.sort = sort;
  if (journalIds.includes(params.get('journal') || '')) result.journal = params.get('journal')!;
  const topic = params.get('topic') || 'all';
  if (topic === 'unknown' || /^https:\/\/openalex\.org\/T\d+$/.test(topic)) result.topic = topic;
  result.query = (params.get('q') || '').slice(0, 150);
  result.hidePublished = params.get('include_published') !== '1';
  return result;
}

export function filterQuery(filters: Filters): string {
  const p = new URLSearchParams();
  if(!filters.hidePublished)p.set('include_published','1');
  for (const [key,value] of [['tab',filters.kind],['window',filters.window],['sort',filters.sort],['journal',filters.journal],['topic',filters.topic],['q',filters.query]]) {
    if (value) p.set(key,value);
  }
  return '?' + p.toString();
}

export function numberLabel(value: number | null, locale: string): string {
  if (value === null) return '—';
  return new Intl.NumberFormat(locale === 'zh' ? 'zh-CN' : 'en', { notation: value >= 1000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value);
}

export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[ch]!);
}

export function doiUrl(doi: string): string {
  return /^10\.\d{4,9}\/[^\s<>"#?]+$/i.test(doi) ? 'https://doi.org/' + encodeURI(doi) : '';
}
