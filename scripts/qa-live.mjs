// GPL-3.0-only. Browser checks against the actual snapshot, never synthetic data.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { chromium, devices, expect } from '@playwright/test';
import { defaults, filtered, sortPapers } from '../src/discovery.ts';
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:4173/neuro-paper-radar/';
const browser = await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||undefined});
const evidence=[];
try {
  for (const [name,settings] of [['desktop',{viewport:{width:1440,height:1000}}],['mobile',{...devices['iPhone 13']}]] ) {
    const context=await browser.newContext(settings);const page=await context.newPage();const errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    const response=await page.goto(base,{waitUntil:'networkidle'});assert.equal(response.status(),200);
    const dataResponse=await context.request.get(new URL('data/papers.json',base).href);assert.equal(dataResponse.status(),200);
    const data=await dataResponse.json();assert.ok(data.coverage.total>0,'Actual production corpus is required');
    if(process.env.QA_REQUIRE_PUBLISHED_READERS==='1'){
      for(const id of ['elife','plos-biology','plos-computational-biology','plos-one'])
        assert.ok(data.papers.some(p=>p.journal_id===id && p.accesses.value!==null && p.accesses.value>0),`${id} requires a positive verified real readership measurement`);
    }
    let build=null;
    if(base.startsWith('https:')){
      const buildResponse=await context.request.get(new URL('build-info.json',base).href,{headers:{'Cache-Control':'no-cache'}});
      assert.equal(buildResponse.status(),200);build=await buildResponse.json();
      assert.match(build.commit,/^[a-f0-9]{40}$/);assert.equal(build.papers,data.coverage.total);
      if(process.env.QA_EXPECTED_COMMIT && build.commit!==process.env.QA_EXPECTED_COMMIT){
        // A serialized data refresh may publish while this live QA job starts.
        // Accept only an actual descendant with exclusively the three data files
        // changed. Any code/workflow change still fails the verified revision check.
        execFileSync('git',['fetch','--no-tags','origin',build.commit],{stdio:'pipe'});
        execFileSync('git',['merge-base','--is-ancestor',process.env.QA_EXPECTED_COMMIT,build.commit],{stdio:'pipe'});
        const changed=execFileSync('git',['diff','--name-only',process.env.QA_EXPECTED_COMMIT,build.commit],{encoding:'utf8'}).trim().split('\n');
        assert.ok(changed.length && changed.every(p=>['public/data/papers.json','data/state.json.gz','data/coverage.json'].includes(p)),'The published descendant must contain only validated refresh data');
        build.validated_code_commit=process.env.QA_EXPECTED_COMMIT;
      }
    }
    await page.locator('#window').selectOption('1y');
    const preprints=filtered(data.papers,{...defaults,window:'1y'});
    const preprintCount=preprints.length;
    await expect(page.locator('.paper')).toHaveCount(Math.min(40,preprintCount),{timeout:30000});
    assert.equal(await page.locator('.coverage-notice').count(),1);
    const measuredPreprints=sortPapers(preprints.filter(p=>p.accesses.value!==null),'accesses');
    if(measuredPreprints.length){
      assert.equal(await page.locator('.paper-title').first().getAttribute('href'),'https://doi.org/'+measuredPreprints[0].doi);
      await expect(page.locator('.sort-description')).toContainText('Readership');
      await expect(page.locator('.reader-available')).toContainText(`${measuredPreprints.length}/${preprintCount}`);
    }
    await expect(page.locator('#hide-published')).toBeChecked();
    await page.locator('#hide-published').uncheck();assert.match(page.url(),/include_published=1/);
    await page.locator('#hide-published').check();
    if(preprintCount>40){await page.locator('[data-more]').click();assert.equal(await page.locator('.paper').count(),Math.min(80,preprintCount));}
    await page.locator('#window').selectOption('today');await page.locator('#window').selectOption('7d');
    await page.goBack();assert.equal(await page.locator('#window').inputValue(),'today');
    await page.goForward();assert.equal(await page.locator('#window').inputValue(),'7d');
    await page.locator('#window').selectOption('1y');await page.locator('#published-tab').click();
    const journalEvidence=[];
    for(const journal of data.coverage.by_journal){
      await page.locator('#journal').selectOption(journal.id);
      const inView=filtered(data.papers,{...defaults,kind:'published',window:'1y',journal:journal.id});
      assert.equal(await page.locator('.paper').count(),Math.min(40,inView.length));
      const measurements=sortPapers(inView.filter(p=>p.accesses.value!==null),'accesses');
      if(measurements.length){
        assert.equal(await page.locator('.paper-title').first().getAttribute('href'),'https://doi.org/'+measurements[0].doi);
        await expect(page.locator('.published-reader')).toBeVisible();
        if(journal.id.startsWith('plos-'))await expect(page.locator('.reader-attribution').first()).toHaveText('Data Provided by PLOS');
        if(journal.id==='elife')await expect(page.locator('.paper').first()).toContainText('all versions');
      }
      journalEvidence.push({journal:journal.id,count:journal.count,in_current_year_view:inView.length,measured_views:measurements.length,top_views_doi:measurements[0]?.doi,top_views:measurements[0]?.accesses.value});
    }
    await page.locator('#journal').selectOption('all');
    assert.equal(await page.locator('.paper').count(),Math.min(40,filtered(data.papers,{...defaults,kind:'published',window:'1y'}).length));
    const first=data.coverage.published?await page.locator('.paper-title').first().textContent():null;
    if(first){
      const link=page.locator('.paper-title').first();assert.match(await link.getAttribute('href'),/^https:\/\/doi\.org\/10\./);
      assert.equal(await link.getAttribute('target'),'_blank');assert.equal(await link.getAttribute('rel'),'noopener noreferrer');
      await page.locator('#search').fill(first.trim().slice(0,65));assert.ok(await page.locator('.paper').count()>0);
    }
    await page.locator('#search').fill('this-query-deliberately-matches-no-paper-702343');
    assert.equal(await page.locator('.paper').count(),0);await page.locator('[data-reset]').click();
    await page.locator('#locale').click();assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');
    await page.reload({waitUntil:'networkidle'});assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');
    await page.locator('#locale').click();assert.equal(await page.locator('html').getAttribute('lang'),'en');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    assert.deepEqual(errors,[]);
    fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:`test-results/live-${name}.png`,fullPage:false});
    evidence.push({device:name,http:response.status(),build_commit:build?.commit,build_workflow_run:build?.workflow_run,papers:data.coverage.total,preprints:data.coverage.preprints,preprints_without_known_published_doi:preprintCount,measured_unlinked_preprints:measuredPreprints.length,top_read_preprint:measuredPreprints[0]?.doi,published:data.coverage.published,data_generated_at:data.generated_at,journals:journalEvidence,console_errors:errors});
    await context.close();
  }
  fs.writeFileSync('test-results/live-qa.json',JSON.stringify({url:base,checked_at:new Date().toISOString(),evidence},null,2)+'\n');
  console.log(JSON.stringify({url:base,evidence},null,2));
} finally {await browser.close();}
