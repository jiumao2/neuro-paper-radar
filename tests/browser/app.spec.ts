import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { Snapshot, Paper } from '../../src/types';

const stamp = new Date().toISOString(), today=stamp.slice(0,10), yesterday=new Date(Date.now()-86400000).toISOString().slice(0,10);
function paper(id:string, kind:Paper['kind'], count:number|null, day=today):Paper {
  return {id:'10.1234/'+id,doi:'10.1234/'+id,kind,title:'TEST FIXTURE — '+id+' neural circuits',authors:['Ada Example','Bo Test'],date:day,date_source:'test fixture',journal_id:kind==='preprint'?'biorxiv':'nature-neuroscience',journal:kind==='preprint'?'bioRxiv':'Nature Neuroscience',article_url:'https://doi.org/10.1234/'+id,topics:id==='measured'?[{id:'https://openalex.org/T123',name:'Memory circuits',score:.8,field_id:'https://openalex.org/fields/28',source:'OpenAlex',automatic:true}]:[],keywords:['memory'],versions:kind==='preprint'?[{version:1,date:day}]:[],related_doi:null,abstract:null,abstract_license:null,metadata_observed_at:stamp,classification:{method:'test fixture',evidence:'neuroscience',automatic:false},provenance:[{source:'OpenAlex',url:'https://openalex.org/W123',observed_at:stamp,license:'CC0-1.0'}],accesses:{value:null,source:null,observed_at:null},citations:{value:count,source:'OpenAlex',observed_at:count===null?null:stamp,work_id:count===null?undefined:'https://openalex.org/W123'}};
}
const fixture: Snapshot = {schema_version:1,generated_at:stamp,papers:[paper('measured','preprint',1250),paper('zero','preprint',0,yesterday),paper('missing','preprint',null),paper('published','published',12)],coverage:{total:4,preprints:3,published:1,accesses:0,citations:3,topics:1,abstracts:0,requested_start:yesterday,requested_end:today,oldest:yesterday,newest:today,excluded:{},by_journal:[{id:'nature-neuroscience',name:'Nature Neuroscience',count:1,candidates:1,oldest:today,newest:today}]},sources:[{id:'biorxiv',status:'ok',last_success:stamp,checked_at:stamp,rows:3,requested_start:yesterday,requested_end:today,errors:[]}],readership:{status:'unavailable',measured:0,reason:'fixture'},schedule:{metadata_hours:6,citations:'daily',repair:'weekly',last_citations:stamp,last_repair:stamp}};
test.beforeEach(async({page})=>{await page.route('**/data/papers.json',route=>route.fulfill({json:fixture}));});

test('filters repeat, URL history works, zero differs from missing, links are safe',async({page})=>{
  await page.goto('./');await expect(page.locator('.paper')).toHaveCount(3);
  await expect(page.locator('.coverage-notice')).toContainText('unavailable');
  await expect(page.locator('.sort-description')).toContainText('Showing Citations');
  await expect(page.locator('.paper').first()).toContainText('1.3K');
  await expect(page.locator('.paper').nth(1).locator('.metric-value').last()).toHaveText('0');
  await expect(page.locator('.paper').last().locator('.rank')).toHaveAttribute('title','Unranked');
  const title=page.locator('.paper-title').first();await expect(title).toHaveAttribute('href','https://doi.org/10.1234/measured');
  await expect(title).toHaveAttribute('target','_blank');await expect(title).toHaveAttribute('rel','noopener noreferrer');
  await page.locator('#window').selectOption('today');await expect(page.locator('.paper')).toHaveCount(2);
  await page.locator('#window').selectOption('7d');await expect(page.locator('.paper')).toHaveCount(3);
  await page.goBack();await expect(page.locator('#window')).toHaveValue('today');await expect(page.locator('.paper')).toHaveCount(2);
  await page.goForward();await expect(page.locator('#window')).toHaveValue('7d');
  await page.locator('#topic').selectOption('unknown');await expect(page.locator('.paper')).toHaveCount(2);
  await page.locator('#topic').selectOption('https://openalex.org/T123');await expect(page.locator('.paper')).toHaveCount(1);
  await page.locator('#topic').selectOption('all');await page.locator('#sort').selectOption('newest');
  await page.locator('#search').fill('no such fixture');await expect(page.getByText('No papers match these filters.')).toBeVisible();
  await page.getByRole('button',{name:'Reset filters'}).click();await expect(page.locator('.paper')).toHaveCount(3);
  await page.getByRole('tab',{name:'Published'}).click();await expect(page.locator('.paper')).toHaveCount(1);
  await page.locator('#journal').selectOption('nature-neuroscience');await expect(page.locator('.paper')).toHaveCount(1);
  await expect(page).toHaveURL(/journal=nature-neuroscience/);
  await page.getByRole('tab',{name:'Preprints'}).click();await expect(page.locator('#journal')).toHaveValue('all');
  await page.getByRole('tab',{name:'Published'}).click();await expect(page.locator('#journal')).toHaveValue('nature-neuroscience');
});

test('locale persists, original titles stay original, abstract expansion is separate',async({page})=>{
  await page.goto('./');await expect(page.locator('.paper')).toHaveCount(3);
  await page.locator('.paper').first().getByText('Abstract',{exact:true}).click();
  await expect(page.locator('.paper').first()).toContainText('Abstract reuse permission is not recorded.');
  await expect(page.getByRole('link',{name:'Read abstract at source'})).toHaveAttribute('href','https://doi.org/10.1234/measured');
  await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('lang','zh-CN');
  await expect(page.locator('.paper-title').first()).toContainText('TEST FIXTURE');
  await page.reload();await expect(page.getByRole('button',{name:'English',exact:true})).toBeVisible();
  await expect(page.locator('#window')).toHaveValue('30d');
  await page.getByRole('button',{name:'English',exact:true}).click();
  await expect(page.locator('html')).toHaveAttribute('lang','en');
});

test('last-good browser data survives refresh failure and fresh errors can recover',async({page})=>{
  await page.goto('./');await expect(page.locator('.paper')).toHaveCount(3);
  await page.route('**/data/papers.json',route=>route.fulfill({status:503,body:'Unavailable'}));
  await page.reload();await expect(page.locator('.paper')).toHaveCount(3);await expect(page.locator('.error-notice')).toContainText('last-good snapshot');
  await page.evaluate(async()=>{await new Promise<void>((resolve,reject)=>{const r=indexedDB.deleteDatabase('neuro-paper-radar');r.onsuccess=()=>resolve();r.onerror=()=>reject();});});
  await page.reload();await expect(page.getByText('Paper data could not be loaded.')).toBeVisible();
  await page.route('**/data/papers.json',route=>route.fulfill({json:fixture}));
  await page.getByRole('button',{name:'Retry data refresh'}).click();await expect(page.locator('.paper')).toHaveCount(3);
});

test('malformed HTTP200 never replaces the last-good snapshot',async({page})=>{
  await page.goto('./');await expect(page.locator('.paper')).toHaveCount(3);
  const malformed={...fixture,papers:fixture.papers.map(p=>({...p,versions:undefined,classification:undefined})),coverage:{...fixture.coverage,by_journal:undefined}};
  await page.route('**/data/papers.json',route=>route.fulfill({json:malformed}));
  await page.reload();await expect(page.locator('.paper')).toHaveCount(3);await expect(page.locator('.error-notice')).toContainText('last-good snapshot');
  await page.route('**/data/papers.json',route=>route.fulfill({status:503,body:'offline'}));
  await page.reload();await expect(page.locator('.paper')).toHaveCount(3);
});

test('a throwing localStorage property getter still allows startup and locale changes',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Denied','SecurityError');}});});
  await page.goto('./');await expect(page.locator('.paper')).toHaveCount(3);
  await page.getByRole('button',{name:'中文',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('lang','zh-CN');
  await page.getByRole('button',{name:'English',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('lang','en');
});

test('partial and empty snapshots are explicit, desktop/mobile have no horizontal overflow',async({page})=>{
  await page.route('**/data/papers.json',route=>route.fulfill({json:{...fixture,sources:[{...fixture.sources[0],status:'failed',errors:['Official API temporarily unavailable']}]}}));
  await page.goto('./');await expect(page.locator('.partial-notice')).toBeVisible();
  await page.locator('#methodology>summary').click();await expect(page.getByText('Official API temporarily unavailable')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.route('**/data/papers.json',route=>route.fulfill({json:{...fixture,papers:[],coverage:{...fixture.coverage,total:0,preprints:0,published:0,citations:0,topics:0}}}));
  await page.reload();await expect(page.getByText('No papers match these filters.')).toBeVisible();
});

test('accessible controls and keyboard tab changes',async({page})=>{
  await page.goto('./');await expect(page.locator('.paper')).toHaveCount(3);
  const accessibility=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.locator('#preprints-tab').focus();await page.keyboard.press('ArrowRight');
  await expect(page.locator('#published-tab')).toHaveAttribute('aria-selected','true');
  await page.screenshot({path:`test-results/${test.info().project.name}-overview.png`,fullPage:true});
});
