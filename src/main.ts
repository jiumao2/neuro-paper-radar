import './style.css';
import type { Filters, Locale, Paper, Snapshot, Sort } from './types';
import { dateWindow, doiUrl, escapeHtml as h, filtered, filterQuery, numberLabel, ranks, readFilters, resolvedSort, sortPapers, sorts, windows } from './discovery';
import { saveLocale, storedLocale, translator } from './i18n';
import { loadSnapshot } from './data';

const root = document.querySelector<HTMLDivElement>('#app')!;
const localeStorage = () => { try { return window.localStorage; } catch { return null; } };
let locale: Locale = storedLocale(localeStorage());
let filters: Filters = readFilters(window.location.search);
let snapshot: Snapshot | null = null;
let loading = true, cached = false, visible = 40;
const expanded = new Set<string>();
const icon = (name: 'search' | 'arrow' | 'info' | 'refresh') => ({
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  arrow:'<path d="M7 17 17 7M7 7h10v10"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1"/>',
})[name];
const svg = (name: 'search' | 'arrow' | 'info' | 'refresh') => `<svg viewBox="0 0 24 24" aria-hidden="true">${icon(name)}</svg>`;
const t = () => translator(locale);
const fmtDate = (date: string | null | undefined, time=false) => date ? new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en', {
  year:'numeric', month:'short', day:'numeric', ...(time ? {hour:'2-digit',minute:'2-digit'} as const : {}), timeZone:'UTC',
}).format(new Date(date.length === 10 ? date + 'T00:00:00Z' : date)) + (time ? ' UTC' : '') : t()('noData');
const external = (url: string, label: string, className='') => `<a href="${h(url)}" target="_blank" rel="noopener noreferrer" class="${className}">${label}${svg('arrow')}</a>`;

function paperMarkup(p: Paper, index: number, rank: number | null, by: Sort): string {
  const tr = t(), detailId = `details-${index}`, abstractId = `abstract-${index}`;
  const authors = p.authors.length > 4 ? p.authors.slice(0,4).join(', ') + ` +${p.authors.length-4}` : p.authors.join(', ');
  const topics = p.topics.length ? p.topics.slice(0,2).map(topic => `<button class="topic-pill" data-topic="${h(topic.id)}" title="${h(tr('filterTopic') + ': ' + topic.name + ' · OpenAlex ' + topic.score)}">${h(topic.name)}</button>`).join('') : `<span class="topic-pill unknown">${tr('unknown')}</span>`;
  const metrics = (['accesses','citations'] as const).map(key => {
    const m = p[key], measured = m.value !== null;
    const tip = measured ? `${new Intl.NumberFormat(locale).format(m.value!)} · ${m.source} · ${tr('observed')}: ${fmtDate(m.observed_at,true)}` : tr(key === 'accesses' ? 'accessMissing' : 'citationsMissing');
    return `<div class="metric ${by === key ? 'active' : ''} ${measured ? '' : 'missing'}"><span class="metric-value" title="${h(tip)}">${numberLabel(m.value,locale)}</span><span class="metric-label">${tr(key)}</span></div>`;
  }).join('');
  const details = `<details id="${detailId}" data-remember="${h(p.id)}-details" ${expanded.has(p.id+'-details') ? 'open' : ''}><summary>${tr('details')}</summary><div class="paper-details">
    <p><strong>${tr('showAllAuthors')}:</strong> ${h(p.authors.join(', ') || '—')}</p>
    <p><strong>${tr('metadataObserved')}:</strong> ${h(fmtDate(p.metadata_observed_at,true))} · ${h(p.date_source)}</p>
    <p><strong>${tr('accesses')}:</strong> ${p.accesses.value === null ? tr('accessMissing') : h(p.accesses.definition)}${p.accesses.observed_at ? ` · ${tr('observed')}: ${h(fmtDate(p.accesses.observed_at,true))}` : ''}</p>
    <p><strong>${tr('citations')}:</strong> ${p.citations.value === null ? tr('citationsMissing') : `${h(p.citations.source)} · ${h(fmtDate(p.citations.observed_at,true))}`}. ${tr('methods3')}</p>
    ${p.citations.work_id ? `<p>${external(p.citations.work_id, h(p.citations.work_id), 'text-link')}</p>` : ''}
    <p>${h(p.classification.method)} · ${h(Array.isArray(p.classification.evidence) ? p.classification.evidence.join(', ') : p.classification.evidence)}</p>
    ${p.topics.length ? `<p>${tr('topicUncertainty')}</p><ul>${p.topics.map(topic => `<li>${h(topic.name)} · OpenAlex ${topic.score} · ${tr('automatic')}</li>`).join('')}</ul>` : `<p>${tr('unknown')}</p>`}
    ${p.versions.length ? `<p>${p.versions.map(v => `${tr('version')} ${v.version}: ${fmtDate(v.date)}`).map(h).join(' · ')}</p>` : ''}
    <p class="provenance">${p.provenance.map(source => external(source.url,`${h(source.source)} (${h(source.license)})`,'text-link')).join(' · ')}</p>
  </div></details>`;
  const abstract = `<details id="${abstractId}" data-remember="${h(p.id)}-abstract" ${expanded.has(p.id+'-abstract') ? 'open' : ''}><summary>${tr('abstract')}</summary><div class="abstract-text">${p.abstract ? `<p>${h(p.abstract)}</p><p class="muted">${tr('abstractLicense')}: ${h(p.abstract_license)} · ${h(p.authors.join(', '))} · ${external(doiUrl(p.doi), h(p.journal),'text-link')}</p>` : `<p>${tr('abstractMissing')}</p>${external(doiUrl(p.doi),tr('atSource'),'text-link')}`}</div></details>`;
  return `<article class="paper" aria-labelledby="title-${index}"><div class="rank" title="${rank === null ? tr('unranked') : tr(by)}">${rank === null ? '<span aria-label="'+tr('unranked')+'">—</span>' : `<span class="sr-only">${tr(by)} </span>${String(rank).padStart(2,'0')}`}</div>
    <div class="paper-body"><div class="paper-meta"><span class="journal-dot ${p.kind}"></span><span>${h(p.journal)}</span><span class="meta-divider">/</span><span>${tr(p.kind === 'preprint' ? 'firstV1' : 'online')} ${h(fmtDate(p.date))}</span>${p.versions.length > 1 ? `<span class="revision">v${Math.max(...p.versions.map(v=>v.version))}</span>` : ''}</div>
      <h3 id="title-${index}">${external(doiUrl(p.doi),h(p.title),'paper-title')}</h3><p class="authors" title="${h(p.authors.join(', '))}">${h(authors || '—')}</p>
      <div class="topics">${topics}</div><div class="paper-actions">${abstract}${details}${p.related_doi ? external(doiUrl(p.related_doi),tr('related'),'related-link') : ''}</div>
    </div><div class="paper-metrics">${metrics}</div></article>`;
}

function coverageMarkup(): string {
  if (!snapshot) return '';
  const tr = t(), c = snapshot.coverage;
  return `<details class="methodology" id="methodology" data-remember="methodology" ${expanded.has('methodology') ? 'open' : ''}><summary>${tr('sources')}<span>${svg('info')}</span></summary><div class="methodology-body">
    <p>${tr('coverageGap')}</p><div class="coverage-stats"><span><strong>${c.citations}/${c.total}</strong> ${tr('citationCoverage')}</span><span><strong>${c.topics}/${c.total}</strong> ${tr('topicCoverage')}</span><span><strong>${c.accesses}/${c.total}</strong> ${tr('accessCoverage')}</span></div>
    <div class="table-scroll"><table><caption>${tr('byJournal')}</caption><thead><tr><th scope="col">${tr('journal')}</th><th scope="col">${tr('included')}</th><th scope="col">${tr('candidates')}</th><th scope="col">${tr('dates')}</th></tr></thead><tbody>${c.by_journal.map(j => `<tr><th scope="row">${h(j.name)}</th><td>${j.count}</td><td>${j.candidates}</td><td>${h(fmtDate(j.oldest))} — ${h(fmtDate(j.newest))}</td></tr>`).join('')}</tbody></table></div>
    <div class="table-scroll"><table><caption>${tr('source')} API</caption><thead><tr><th scope="col">${tr('source')}</th><th scope="col">${tr('status')}</th><th scope="col">${tr('lastSuccess')}</th></tr></thead><tbody>${snapshot.sources.map(s => `<tr><th scope="row">${h(s.id)}</th><td>${tr(s.status === 'ok' ? 'ok' : s.status === 'failed' ? 'failedStatus' : s.status === 'partial' ? 'partialStatus' : 'pending')}${s.errors.length ? `<p class="source-error">${s.errors.map(h).join('; ')}</p>` : ''}</td><td>${h(fmtDate(s.last_success,true))}</td></tr>`).join('')}</tbody></table></div>
    <p>${tr('methods1')}</p><p>${tr('methods2')}</p><p>${tr('methods3')}</p><p>${tr('methods4')}</p><p>${tr('schedule')}</p>
    <p class="muted">${tr('citations')}: ${h(fmtDate(snapshot.schedule.last_citations,true))} · ${h(snapshot.schedule.repair)}: ${h(fmtDate(snapshot.schedule.last_repair,true))}</p>
  </div></details>`;
}

function render(): void {
  const focus = document.activeElement as HTMLInputElement | HTMLSelectElement | null;
  const focusId = focus?.id, selection = focus instanceof HTMLInputElement ? focus.selectionStart : null;
  const tr = t(), all = snapshot?.papers || [];
  const subset = filtered(all,filters), effective = resolvedSort(subset,filters.sort), ordered = sortPapers(subset,effective), places = ranks(ordered,effective);
  const range = dateWindow(filters.window), topicCounts = new Map<string,{name:string;count:number}>();
  for (const p of all.filter(p=>p.kind === filters.kind)) for (const topic of p.topics) {
    const current = topicCounts.get(topic.id); topicCounts.set(topic.id,{ name:topic.name,count:(current?.count||0)+1 });
  }
  const topicOptions = [...topicCounts].sort((a,b)=>a[1].name.localeCompare(b[1].name));
  if (!['all','unknown'].includes(filters.topic) && !topicCounts.has(filters.topic)) topicOptions.push([filters.topic,{name:filters.topic.split('/').pop()!,count:0}]);
  const stale = snapshot && Date.now() - Date.parse(snapshot.generated_at) > 12*3600000;
  const partial = snapshot?.sources.some(s=>s.status !== 'ok');
  const status = stale ? tr('stale') : partial ? tr('partial') : tr('current');
  const options = (values: readonly string[], selected: string) => values.map(v=>`<option value="${v}" ${v===selected?'selected':''}>${tr(v as 'today')}</option>`).join('');
  root.innerHTML = `<a class="skip-link" href="#results">${tr('skip')}</a>
    <header class="site-header"><div class="header-inner"><a class="brand" href="${import.meta.env.BASE_URL}" aria-label="NeuroPaper Radar"><img src="${import.meta.env.BASE_URL}radar.svg" alt="" width="40" height="40"/><span>NeuroPaper<span class="brand-light"> Radar</span><small>${tr('tagline')}</small></span></a><nav aria-label="Navigation"><button id="locale" class="locale-button" lang="${locale === 'en' ? 'zh-CN' : 'en'}">${locale === 'en' ? '中文' : 'English'}</button>${external('https://github.com/jiumao2/neuro-paper-radar','GitHub','repo-link')}</nav></div></header>
    <main><section class="hero" aria-labelledby="heading"><div class="hero-copy"><p class="eyebrow"><span></span>${tr('eyebrow')}</p><h1 id="heading">${tr('heading')}<br/><em>${tr('headingAccent')}</em></h1><p class="intro">${tr('intro')}</p></div><div class="hero-art" aria-hidden="true"><div class="orbit orbit-1"></div><div class="orbit orbit-2"></div><div class="orbit orbit-3"></div><div class="orbit-axis"></div><span class="orbital-dot d1"></span><span class="orbital-dot d2"></span><span class="orbital-dot d3"></span></div><div class="hero-stats"><div><strong>${snapshot ? numberLabel(snapshot.coverage.preprints,locale) : '—'}</strong><span>${tr('preprints')}</span></div><div><strong>${snapshot ? numberLabel(snapshot.coverage.published,locale) : '—'}</strong><span>${tr('published')}</span></div><div><strong>5</strong><span>${tr('journals')}</span></div></div></section>
    <section class="discovery" aria-labelledby="results-heading"><div class="tabs" role="tablist" aria-label="${tr('results')}"><button id="preprints-tab" role="tab" aria-selected="${filters.kind==='preprint'}" aria-controls="results" tabindex="${filters.kind==='preprint'?0:-1}" data-kind="preprint">${tr('preprints')}<span>bioRxiv</span></button><button id="published-tab" role="tab" aria-selected="${filters.kind==='published'}" aria-controls="results" tabindex="${filters.kind==='published'?0:-1}" data-kind="published">${tr('published')}<span>5 ${tr('journals')}</span></button></div>
      <div class="search-row"><div class="search-field">${svg('search')}<label for="search" class="sr-only">${tr('searchLabel')}</label><input id="search" type="search" maxlength="150" value="${h(filters.query)}" placeholder="${tr('search')}" autocomplete="off"/></div><div class="snapshot-stamp ${stale||partial?'warning':''}"><span class="status-dot"></span><span>${status}<small>${snapshot ? h(fmtDate(snapshot.generated_at,true)) : tr('loading')}</small></span></div></div>
      <div class="filters"><div class="filter-field"><label for="window">${tr('window')}</label><select id="window">${options(windows,filters.window)}</select></div><div class="filter-field"><label for="journal">${tr('journal')}</label><select id="journal" ${filters.kind==='preprint'?'disabled':''}><option value="all" ${filters.kind==='preprint'||filters.journal==='all'?'selected':''}>${filters.kind==='preprint'?'bioRxiv · '+tr('neuroscience'):tr('allJournals')}</option>${filters.kind==='published'?(snapshot?.coverage.by_journal.map(j=>`<option value="${j.id}" ${filters.journal===j.id?'selected':''}>${h(j.name)}</option>`).join('')||''):''}</select></div><div class="filter-field"><label for="topic">${tr('topic')}</label><select id="topic"><option value="all" ${filters.topic==='all'?'selected':''}>${tr('allTopics')}</option><option value="unknown" ${filters.topic==='unknown'?'selected':''}>${tr('unknown')}</option>${topicOptions.map(([id,v])=>`<option value="${h(id)}" ${filters.topic===id?'selected':''}>${h(v.name)} (${v.count})</option>`).join('')}</select></div><div class="filter-field sort-field"><label for="sort">${tr('sort')}</label><select id="sort">${options(sorts,filters.sort)}</select></div></div>
      ${!snapshot || snapshot.coverage.accesses === 0 ? `<aside class="coverage-notice"><div class="notice-icon">${svg('info')}</div><div><strong>${tr('coverageTitle')}</strong><p>${tr('coverageText')}</p></div><div class="notice-actions"><button data-sort="citations">${tr('useCitations')} <span>→</span></button><button data-sort="newest">${tr('useNewest')} <span>→</span></button></div></aside>`:''}
      ${cached&&snapshot ? `<div class="error-notice" role="status">${tr('cached')} <button data-retry>${tr('retry')}</button></div>`:''}
      ${partial ? `<div class="partial-notice" role="status">${tr('partial')} · <a href="#methodology">${tr('sources')}</a></div>`:''}
      <div id="results" role="tabpanel" aria-labelledby="${filters.kind==='preprint'?'preprints-tab':'published-tab'}" tabindex="0"><div class="results-heading"><h2 id="results-heading">${ordered.length.toLocaleString(locale)} ${tr(ordered.length===1?'paperSingular':'paper')}</h2><p>${tr('dateRange')}: ${h(fmtDate(range.start))} — ${h(fmtDate(range.end))} <span>UTC</span></p></div><div class="sort-description" role="status">${filters.sort!==effective ? tr('accessFallback') : tr('ordered')} <strong>${tr(effective)} ↓</strong>${effective==='citations'?' · OpenAlex':''}${filters.sort==='citations'&&!ordered.some(p=>p.citations.value!==null)?' · '+tr('fallbackNewest'):''}</div>
      ${loading ? `<div class="empty-state" aria-busy="true">${tr('loading')}</div>` : !snapshot ? `<div class="empty-state error-state" role="alert"><h3>${tr('failed')}</h3><button data-retry class="primary-button">${svg('refresh')}${tr('retry')}</button></div>` : !ordered.length ? `<div class="empty-state"><div class="empty-orbit" aria-hidden="true">◎</div><h3>${tr('empty')}</h3><p>${tr('emptyHelp')}</p><button data-reset class="primary-button">${tr('reset')}</button></div>` : `<div class="list-labels" aria-hidden="true"><span>#</span><span>${tr(filters.kind==='preprint'?'preprints':'published')}</span><span>${tr('accesses')}</span><span>${tr('citations')}</span></div><div class="paper-list">${ordered.slice(0,visible).map((p,i)=>paperMarkup(p,i,places[i],effective)).join('')}</div>${visible<ordered.length?`<div class="more"><span>${tr('show')} ${Math.min(visible,ordered.length)} ${tr('of')} ${ordered.length}</span><button data-more>${tr('showMore')} ↓</button></div>`:''}`}
      <p class="metric-note">${tr('metricNote')}</p></div>${coverageMarkup()}
    </section></main><footer><div><span class="footer-brand">NeuroPaper Radar</span><p>${tr('inspired')} ${external('https://github.com/RobertoDF/biorxiv-top','biorxiv-top','text-link')}</p><p>${tr('license')}</p></div>${external('https://github.com/jiumao2/neuro-paper-radar',tr('repo'),'text-link')}</footer>`;
  document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
  document.title = locale === 'zh' ? 'NeuroPaper Radar — 神经科学论文雷达' : 'NeuroPaper Radar — neuroscience, in view';
  if (focusId) {
    const element = document.getElementById(focusId);
    element?.focus({preventScroll:true});
    if (selection!==null && element instanceof HTMLInputElement && element.type==='search') element.setSelectionRange(selection,selection);
  }
}

function update(next: Partial<Filters>, replace=false): void {
  filters = { ...filters,...next }; visible = 40;
  window.history[replace?'replaceState':'pushState'](null,'',filterQuery(filters));
  render();
}

root.addEventListener('change',event => {
  const element = event.target as HTMLSelectElement;
  if (['window','journal','topic','sort'].includes(element.id)) update({ [element.id]:element.value });
});
root.addEventListener('input',event => {
  const element = event.target as HTMLInputElement;
  if (element.id === 'search') update({ query:element.value.slice(0,150) },true);
});
root.addEventListener('click',event => {
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button');
  if (!button) return;
  if (button.id==='locale') { locale=locale==='en'?'zh':'en';saveLocale(locale,localeStorage());render(); }
  if (button.dataset.kind) update({ kind:button.dataset.kind as Filters['kind'] });
  if (button.dataset.sort) update({ sort:button.dataset.sort as Sort });
  if (button.dataset.topic) update({ topic:button.dataset.topic });
  if ('reset' in button.dataset) { filters=readFilters('');update(filters); }
  if ('more' in button.dataset) { visible+=40;render(); }
  if ('retry' in button.dataset) void load();
});
root.addEventListener('toggle',event => {
  const element = event.target as HTMLDetailsElement;
  if (element.dataset.remember) {
    if (element.open) expanded.add(element.dataset.remember); else expanded.delete(element.dataset.remember);
  }
},true);
root.addEventListener('keydown',event => {
  const element = event.target as HTMLElement;
  if (element.getAttribute('role') === 'tab' && ['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
    event.preventDefault();
    const kind = event.key==='Home'?'preprint':event.key==='End'?'published':filters.kind==='preprint'?'published':'preprint';
    update({kind});document.getElementById(kind==='preprint'?'preprints-tab':'published-tab')?.focus();
  }
});
window.addEventListener('popstate',()=>{filters=readFilters(window.location.search);visible=40;render();});

async function load(): Promise<void> {
  loading=!snapshot;render();
  const result = await loadSnapshot(snapshot);snapshot=result.data;cached=result.cached;loading=false;render();
}
void load();
