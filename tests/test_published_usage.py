import copy
import json
import unittest
from pathlib import Path

from ingest.http import Client, SourceError
from ingest.model import crossref_paper
from ingest.published_usage import plos_paper, collect_plos, elife_id, elife_history, elife_measurement, refresh_elife
from ingest.refresh import make_snapshot

STAMP='2026-10-10T19:00:00Z'
CONFIG=json.loads((Path(__file__).parents[1]/'config/sources.json').read_text())
PLOS=next(j for j in CONFIG['journals'] if j['id']=='plos-biology')
ELIFE=next(j for j in CONFIG['journals'] if j['id']=='elife')


def row(identifier='10.1371/journal.pbio.fixture',count=14):
    return {'id':identifier,'doc_type':'full','eissn':'1545-7885','pissn':'1544-9173',
            'title_display':'TEST FIXTURE neural circuit','author_display':['Author Example'],
            'publication_date':'2026-10-08T00:00:00Z','subject':['Biology','Neuroscience'],
            'counter_total_all':count,'counter_total_month':3,'timestamp':'2026-10-09T12:00:00Z'}


def history(vor=True):
    versions=[{'status':'preprint','uri':'https://doi.org/10.1101/2025.07.17.665269','date':'2025-07-21T00:00:00Z'},
              {'status':'preprint','uri':'https://doi.org/10.7554/eLife.108246.1','date':'2025-09-24T00:00:00Z'}]
    if vor: versions.append({'status':'vor','stage':'published','doi':'10.7554/eLife.108246','published':'2026-10-09T00:00:00Z','versionDate':'2026-10-10T00:00:00Z'})
    return {'versions':versions}


def elife_paper():
    return crossref_paper({'DOI':'10.7554/eLife.108246.3','published-online':{'date-parts':[[2026,10,9]]},
                           'created':{'date-time':'2025-09-24T00:00:00Z'},'title':['TEST FIXTURE'],
                           'ISSN':['2050-084X'],'type':'journal-article'},ELIFE,STAMP)


def work():
    return {'topics':[{'id':'https://openalex.org/T123','name':'Neural circuits','score':.9,'field_id':CONFIG['neuroscience_field_id'],'source':'OpenAlex','automatic':True}],
            'keywords':[],'id':'https://openalex.org/W123','citations':{'value':3,'source':'OpenAlex','observed_at':STAMP}}


class PublishedUsageTests(unittest.TestCase):
    def test_plos_metrics_dates_attribution_zero_and_missing(self):
        p=plos_paper(row(),PLOS,STAMP)
        self.assertEqual(p['date'],'2026-10-08');self.assertEqual(p['accesses']['value'],14)
        self.assertEqual(p['accesses']['recent_30_days']['value'],3)
        self.assertEqual(p['accesses']['attribution'],'Data Provided by PLOS')
        self.assertEqual(p['accesses']['observed_at'],STAMP)
        self.assertNotEqual(p['accesses']['observed_at'],p['accesses']['source_indexed_at'])
        self.assertEqual(plos_paper(row(count=0),PLOS,STAMP)['accesses']['value'],0)
        self.assertIsNone(plos_paper(row(count=None),PLOS,STAMP)['accesses']['value'])
        with self.assertRaises(ValueError):plos_paper(row(count=True),PLOS,STAMP)

    def test_plos_fragments_journal_and_taxonomy_are_verified(self):
        for changes in ({'doc_type':'partial'},{'doc_partial_parent_id':'parent'},{'eissn':'0000-0000','pissn':None},{'subject':['Cancer']},{'publication_date':'2026-10'}):
            self.assertIsNone(plos_paper({**row(),**changes},PLOS,STAMP))

    def test_plos_stored_taxonomy_paths_and_singleton_field_arrays(self):
        real_shape={**row(),'doc_type':['full'],'subject':['/Biology and life sciences/Neuroscience/Neurophysiology/Neural signaling'],
                    'publication_date':['2026-10-08T00:00:00Z'],'eissn':['1545-7885'],'id':None,'doi':['10.1371/journal.pbio.fixture']}
        p=plos_paper(real_shape,PLOS,STAMP)
        self.assertEqual(p['id'],'10.1371/journal.pbio.fixture')
        self.assertIn('/Neuroscience/',p['publisher_categories'][0])
        self.assertIsNone(plos_paper({**real_shape,'subject':['/Medicine/Neuroscience-adjacent/Cancer']},PLOS,STAMP))
        self.assertIsNone(plos_paper({**real_shape,'doc_type':['full','partial']},PLOS,STAMP))

    def test_elife_requests_negotiate_documented_vendor_media_types(self):
        requests=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{}'
        def open_request(request,**kwargs):requests.append(request);return Response()
        client=Client(opener=open_request,sleeper=lambda n:None,clock=lambda:0)
        client.get('https://api.elifesciences.org/articles/108246/versions')
        client.get('https://api.elifesciences.org/metrics/article/108246/page-views?by=month&per-page=1')
        self.assertEqual(requests[0].get_header('Accept'),'application/vnd.elife.article-history+json;version=2')
        self.assertEqual(requests[1].get_header('Accept'),'application/vnd.elife.metric-time-period+json;version=1')

    def test_plos_actual_pagination_and_dedup_preserve_last_good(self):
        state={'published':{}}
        class Pages:
            def __init__(self):self.calls=[]
            def get(self,url):
                self.calls.append(url)
                return {'response':{'numFound':4,'docs':[row(),{**row('10.1371/journal.pbio.fragment'),'doc_type':'partial'}] if len(self.calls)==1 else [row(),row('10.1371/journal.pbio.second',0)]}}
        client=Pages();report={'rows':0,'excluded':{}}
        collect_plos(client,PLOS,'2025-10-10','2026-10-10',state,STAMP,report)
        self.assertIn('start=2',client.calls[1]);self.assertEqual(len(state['published']),2)
        self.assertEqual(report['unique_dois'],2)
        class Missing:
            def get(self,url):return {'response':{'numFound':1,'docs':[row(count=None)]}}
        collect_plos(Missing(),PLOS,'2025-10-10','2026-10-10',state,STAMP,{'rows':0,'excluded':{}})
        self.assertEqual(state['published']['10.1371/journal.pbio.fixture']['accesses']['value'],14)
        before=copy.deepcopy(state['published'])
        class Failing:
            def get(self,url):raise SourceError('temporary failure')
        with self.assertRaises(SourceError):collect_plos(Failing(),PLOS,'2025-10-10','2026-10-10',state,STAMP,{'rows':0,'excluded':{}})
        self.assertEqual(state['published'],before)

    def test_plos_missing_recent_preserves_its_timestamp_with_fresh_total(self):
        original=plos_paper(row(),PLOS,'2026-10-09T10:00:00Z');state={'published':{original['id']:original}}
        class API:
            def get(self,url):return {'response':{'numFound':1,'docs':[{**row(count=20),'counter_total_month':None}]}}
        collect_plos(API(),PLOS,'2025-10-10','2026-10-10',state,STAMP,{'rows':0,'excluded':{}})
        m=state['published'][original['id']]['accesses']
        self.assertEqual(m['value'],20);self.assertEqual(m['observed_at'],STAMP)
        self.assertEqual(m['recent_30_days']['value'],3)
        self.assertEqual(m['recent_30_days']['observed_at'],'2026-10-09T10:00:00Z')

    def test_plos_missing_total_does_not_discard_fresh_recent(self):
        original=plos_paper(row(),PLOS,'2026-10-09T10:00:00Z');state={'published':{original['id']:original}}
        class API:
            def get(self,url):return {'response':{'numFound':1,'docs':[{**row(count=None),'counter_total_month':0}]}}
        collect_plos(API(),PLOS,'2025-10-10','2026-10-10',state,STAMP,{'rows':0,'excluded':{}})
        m=state['published'][original['id']]['accesses']
        self.assertEqual(m['value'],14);self.assertEqual(m['observed_at'],'2026-10-09T10:00:00Z')
        self.assertEqual(m['recent_30_days']['value'],0);self.assertEqual(m['recent_30_days']['observed_at'],STAMP)

    def test_global_plos_rate_and_endpoint_row_limits(self):
        now=[0.0];sleeps=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"response":{}}'
        def sleep(seconds):sleeps.append(seconds);now[0]+=seconds
        client=Client(opener=lambda *a,**k:Response(),sleeper=sleep,clock=lambda:now[0])
        for journal in ('1545-7885','1932-6203','1553-7358'):
            client.get('https://api.plos.org/search?q='+journal+'&rows=100')
        self.assertEqual(sleeps,[12.1,12.1])
        with self.assertRaises(SourceError):client.get('https://api.plos.org/search?rows=101')
        with self.assertRaises(SourceError):client.get('https://journals.plos.org/plosbiology/article?id=example')

    def test_elife_canonical_id_and_first_vor_not_reviewed_or_created(self):
        self.assertEqual(elife_id('10.7554/eLife.108246.4'),'108246')
        p=elife_paper();self.assertEqual(p['id'],'10.7554/elife.108246')
        parsed=elife_history(history(),'108246')
        self.assertEqual(parsed['vor_date'],'2026-10-09')
        self.assertEqual(parsed['reviewed_preprint_date'],'2025-09-24')
        self.assertIsNone(elife_history(history(False),'108246')['vor_date'])
        preview=history();preview['versions'][-1]['stage']='preview'
        self.assertIsNone(elife_history(preview,'108246')['vor_date'])

    def test_elife_total_is_cumulative_not_first_page_or_download_sum(self):
        m=elife_measurement({'totalValue':607,'totalPeriods':14,'periods':[{'period':'2026-10','value':11}]},'108246','page-views',STAMP)
        self.assertEqual(m['value'],607);self.assertIn('all versions',m['definition'])
        self.assertFalse(m['unique_readers'])
        self.assertEqual(elife_measurement({'totalValue':0},'108246','downloads',STAMP)['value'],0)
        self.assertIsNone(elife_measurement({'totalValue':None},'108246','page-views',STAMP)['value'])
        with self.assertRaises(ValueError):elife_measurement({'periods':[]},'108246','page-views',STAMP)

    def test_elife_queue_verifies_vor_keeps_channels_separate_and_retains_failures(self):
        p=elife_paper();state={'published':{p['id']:p},'openalex':{p['id']:work()},'sources':{},'preprints':{}}
        class API:
            def get(self,url):return history() if url.endswith('/versions') else {'totalValue':27 if '/downloads?' in url else 607}
        refresh_elife(API(),state,CONFIG,STAMP,'2025-10-10','2026-10-10')
        self.assertEqual(p['accesses']['value'],607);self.assertEqual(p['downloads']['value'],27)
        self.assertTrue(p['elife_vor_verified']);self.assertEqual(p['date'],'2026-10-09')
        self.assertEqual(make_snapshot(state,CONFIG,STAMP,'2025-10-10','2026-10-10')['coverage']['published'],1)
        before=copy.deepcopy(p['accesses'])
        class Failing:
            def get(self,url):raise SourceError('temporary failure')
        refresh_elife(Failing(),state,CONFIG,'2026-10-11T19:00:00Z','2025-10-10','2026-10-11')
        self.assertEqual(p['accesses'],before);self.assertEqual(state['sources']['elife-api']['status'],'partial')

    def test_reviewed_preprint_only_is_excluded_from_published(self):
        p=elife_paper();state={'published':{p['id']:p},'openalex':{p['id']:work()},'sources':{},'preprints':{}}
        class API:
            def get(self,url):
                if '/metrics/' in url:raise AssertionError('No metrics for reviewed-preprint-only published rows')
                return history(False)
        refresh_elife(API(),state,CONFIG,STAMP,'2025-10-10','2026-10-10')
        snapshot=make_snapshot(state,CONFIG,STAMP,'2025-10-10','2026-10-10')
        self.assertEqual(snapshot['coverage']['published'],0)
        self.assertEqual(snapshot['coverage']['excluded']['elife_vor_unverified_or_reviewed_preprint'],1)

    def test_more_than_350_fresh_negative_histories_do_not_starve_vor(self):
        p=elife_paper();state={'published':{p['id']:p},'openalex':{p['id']:work()},'sources':{},'elife_history':{}}
        for n in range(1,352):
            candidate=copy.deepcopy(p);identifier=f'10.7554/elife.{n}';candidate.update(id=identifier,doi=identifier,article_url='https://doi.org/'+identifier)
            state['published'][identifier]=candidate;state['openalex'][identifier]=work()
            state['elife_history'][str(n)]={'vor_date':None,'reviewed_preprint_date':'2026-10-09','publication_history':[],'checked_at':STAMP}
        class API:
            def get(self,url):
                if '/108246/' not in url:raise AssertionError('Fresh negative histories must not make calls')
                return history() if '/versions' in url else {'totalValue':607}
        refresh_elife(API(),state,CONFIG,STAMP,'2025-10-10','2026-10-10')
        self.assertEqual(p['accesses']['value'],607)
        self.assertEqual(state['sources']['elife-api']['deferred'],0)

    def test_persistent_attempt_order_advances_untried_vor_before_due_negatives(self):
        p=elife_paper();state={'published':{p['id']:p},'openalex':{p['id']:work()},'sources':{},
                             'elife_history':{},'elife_attempts':{}}
        for n in range(1,352):
            candidate=copy.deepcopy(p);identifier=f'10.7554/elife.{n}';candidate.update(id=identifier,doi=identifier)
            state['published'][identifier]=candidate;state['openalex'][identifier]=work()
            state['elife_history'][str(n)]={'vor_date':None,'reviewed_preprint_date':'2026-10-09','publication_history':[],'checked_at':'2026-10-09T00:00:00Z'}
            state['elife_attempts'][str(n)]='2026-10-09T00:00:00Z'
        calls=[]
        class API:
            def get(self,url):
                calls.append(url)
                return history() if '/versions' in url else {'totalValue':607}
        refresh_elife(API(),state,CONFIG,STAMP,'2025-10-10','2026-10-10',limit=1)
        self.assertIn('/108246/',calls[0]);self.assertEqual(p['accesses']['value'],607)
        self.assertEqual(state['elife_attempts']['108246'],STAMP)


if __name__=='__main__':unittest.main()
