import { describe, expect, it } from 'vitest';
import { calendarSubtract, dateWindow, defaults, doiUrl, escapeHtml, filtered, filterQuery, numberLabel, ranks, readFilters, resolvedSort, sortPapers } from './discovery';
import { saveLocale, storedLocale, strings } from './i18n';
import { validSnapshot } from './data';
import type { Paper } from './types';

const paper = (id:string, date='2026-10-10', citations:number|null=null, accesses:number|null=null): Paper => ({
  id,doi:'10.1234/'+id,kind:'preprint',title:'TEST FIXTURE — Neural circuits',authors:['Élodie Chen'],date,date_source:'fixture',journal_id:'biorxiv',journal:'bioRxiv',article_url:'https://doi.org/10.1234/'+id,
  metadata_observed_at:'2026-10-10T00:00:00Z',topics:[],keywords:['memory'],versions:[{version:1,date}],related_doi:null,abstract:null,abstract_license:null,provenance:[],classification:{method:'fixture',evidence:'neuroscience',automatic:false},
  citations:{value:citations,observed_at:null,source:'OpenAlex'},accesses:{value:accesses,observed_at:null,source:null},
});
const now = new Date('2026-10-10T23:59:59Z');

describe('UTC calendar publication windows',()=>{
  it('uses UTC even at timezone boundaries and includes today in 7/30 days',()=>{
    expect(dateWindow('today',new Date('2026-10-11T00:30:00+01:00'))).toEqual({start:'2026-10-10',end:'2026-10-10'});
    expect(dateWindow('7d',now).start).toBe('2026-10-04');
    expect(dateWindow('30d',now).start).toBe('2026-09-11');
  });
  it('clamps leap days and month ends, including cross-year subtraction',()=>{
    expect(calendarSubtract(new Date('2024-05-31Z'),3).toISOString().slice(0,10)).toBe('2024-02-29');
    expect(calendarSubtract(new Date('2025-05-31Z'),3).toISOString().slice(0,10)).toBe('2025-02-28');
    expect(dateWindow('1y',new Date('2024-02-29Z')).start).toBe('2023-02-28');
    expect(dateWindow('6m',new Date('2026-01-31Z')).start).toBe('2025-07-31');
    expect(dateWindow('3m',now).start).toBe('2026-07-10');
  });
  it('excludes future dates and applies inclusive boundaries',()=>{
    const p=[paper('boundary','2026-09-11'),paper('before','2026-09-10'),paper('future','2026-10-11')];
    expect(filtered(p,defaults,now).map(p=>p.id)).toEqual(['boundary']);
  });
});
describe('raw metrics and discovery',()=>{
  it('puts missing after measured zero and never mutates input',()=>{
    const p=[paper('missing'),paper('zero','2026-10-09',0),paper('high','2026-10-08',12)];
    expect(sortPapers(p,'citations').map(p=>p.id)).toEqual(['high','zero','missing']);
    expect(p[0].id).toBe('missing');
    expect(ranks(sortPapers(p,'citations'),'citations')).toEqual([1,2,null]);
  });
  it('shows honest fallback only when every access value is missing',()=>{
    expect(resolvedSort([paper('zero','2026-10-10',0)],'accesses')).toBe('citations');
    expect(resolvedSort([paper('missing')],'accesses')).toBe('newest');
    expect(resolvedSort([paper('access','2026-10-10',null,0)],'accesses')).toBe('accesses');
    expect(resolvedSort([], 'accesses')).toBe('newest');
  });
  it('ties share ranks and missing values stay unranked',()=>{
    const p=[paper('a','2026-10-10',10),paper('b','2026-10-09',10),paper('c','2026-10-10',0),paper('d')];
    expect(ranks(sortPapers(p,'citations'),'citations')).toEqual([1,1,3,null]);
  });
  it('searches author accents and keywords; unknown topics are explicit',()=>{
    expect(filtered([paper('a')],{...defaults,query:'Elodie memory',topic:'unknown'},now)).toHaveLength(1);
    expect(filtered([paper('a')],{...defaults,topic:'https://openalex.org/T1'},now)).toHaveLength(0);
    const p={...paper('a'),kind:'published' as const,journal_id:'nature-methods'};
    expect(filtered([p],{...defaults,kind:'published',journal:'nature'},now)).toHaveLength(0);
    expect(filtered([p],{...defaults,kind:'published',journal:'nature-methods'},now)).toHaveLength(1);
  });
  it('rounds counts while preserving zero and missing; title links stay safe',()=>{
    expect(numberLabel(1250,'en')).toBe('1.3K');expect(numberLabel(0,'en')).toBe('0');expect(numberLabel(null,'zh')).toBe('—');
    expect(doiUrl('javascript:alert(1)')).toBe('');expect(doiUrl('10.64898/new')).toBe('https://doi.org/10.64898/new');
    expect(escapeHtml('<script>"&')).toBe('&lt;script&gt;&quot;&amp;');
  });
});
describe('URL and bilingual state',()=>{
  it('round-trips filters and rejects invalid parameters',()=>{
    const f={...defaults,kind:'published' as const,journal:'nature',sort:'newest' as const,topic:'https://openalex.org/T123',query:'brain & memory'};
    expect(readFilters(filterQuery(f))).toEqual(f);
    expect(readFilters('?window=no&sort=no&journal=nature-fake&topic=javascript:bad')).toEqual(defaults);
  });
  it('both locales have all strings and persist choice, tolerating denied storage',()=>{
    expect(Object.keys(strings.en).sort()).toEqual(Object.keys(strings.zh).sort());
    let value='';const storage={getItem:()=>value,setItem:(_key:string,v:string)=>{value=v;}};
    saveLocale('zh',storage);expect(storedLocale(storage)).toBe('zh');
    expect(storedLocale({getItem:()=>{throw new Error('restricted');}})).toBe('en');
    expect(()=>saveLocale('zh',{setItem:()=>{throw new Error('restricted');}})).not.toThrow();
  });
  it('rejects broken snapshots',()=>{expect(validSnapshot({schema_version:1,papers:[paper('a')],coverage:{total:0},generated_at:'bad'})).toBe(false);});
});
