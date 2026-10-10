// GPL-3.0-only. Browser checks against the actual snapshot, never synthetic data.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium, devices, expect } from '@playwright/test';
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
    await page.locator('#window').selectOption('1y');
    const preprintCount=data.papers.filter(p=>p.kind==='preprint').length;
    await expect(page.locator('.paper')).toHaveCount(Math.min(40,preprintCount),{timeout:30000});
    assert.equal(await page.locator('.coverage-notice').count(),1);
    if(preprintCount>40){await page.locator('[data-more]').click();assert.equal(await page.locator('.paper').count(),Math.min(80,preprintCount));}
    await page.locator('#window').selectOption('today');await page.locator('#window').selectOption('7d');
    await page.goBack();assert.equal(await page.locator('#window').inputValue(),'today');
    await page.goForward();assert.equal(await page.locator('#window').inputValue(),'7d');
    await page.locator('#window').selectOption('1y');await page.locator('#published-tab').click();
    const journalEvidence=[];
    for(const journal of data.coverage.by_journal){
      await page.locator('#journal').selectOption(journal.id);
      assert.equal(await page.locator('.paper').count(),Math.min(40,journal.count));
      journalEvidence.push({journal:journal.id,count:journal.count});
    }
    await page.locator('#journal').selectOption('all');
    assert.equal(await page.locator('.paper').count(),Math.min(40,data.coverage.published));
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
    evidence.push({device:name,http:response.status(),papers:data.coverage.total,preprints:data.coverage.preprints,published:data.coverage.published,data_generated_at:data.generated_at,journals:journalEvidence,console_errors:errors});
    await context.close();
  }
  fs.writeFileSync('test-results/live-qa.json',JSON.stringify({url:base,checked_at:new Date().toISOString(),evidence},null,2)+'\n');
  console.log(JSON.stringify({url:base,evidence},null,2));
} finally {await browser.close();}
