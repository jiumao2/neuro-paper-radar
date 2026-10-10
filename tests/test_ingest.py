import copy
import io
import gzip
import json
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

from ingest.http import Client, SourceError, retry_delay
from ingest.model import (attach_openalex, biorxiv_paper, crossref_paper, doi, exact_date,
                          metric, normalize_work, subtract_months, validate_paper)
from ingest.readership import ApprovedReadershipQueue, validate_import, validated_imports
from ingest.refresh import atomic_bytes, collect_biorxiv, make_snapshot, refresh_openalex, run

CONFIG = json.loads((Path(__file__).parents[1] / 'config/sources.json').read_text())
STAMP = '2026-10-10T12:00:00Z'


def bio(version=1, day='2026-09-01', license='cc_by'):
    return {'doi':'10.64898/2026.09.01.123456','title':'TEST FIXTURE — neurons', 'authors':'A; B',
            'version':str(version),'date':day,'category':'neuroscience','server':'biorxiv',
            'license':license,'abstract':'Fixture abstract','published':'10.1038/s41593-026-12345-x'}


class ModelTests(unittest.TestCase):
    def test_calendar_dates(self):
        self.assertEqual(subtract_months(date(2024,5,31),3),date(2024,2,29))
        self.assertEqual(subtract_months(date(2025,5,31),3),date(2025,2,28))
        self.assertEqual(subtract_months(date(2024,2,29),12),date(2023,2,28))
        self.assertEqual(subtract_months(date(2026,1,31),6),date(2025,7,31))

    def test_doi_and_date_validation(self):
        self.assertEqual(doi('https://doi.org/10.64898/2026.01.01.123456'),'10.64898/2026.01.01.123456')
        self.assertIsNone(doi('javascript:alert(1)'))
        self.assertIsNone(exact_date({'date-parts':[[2026,9]]}))
        self.assertIsNone(exact_date({'date-parts':[[2025,2,29]]}))
        self.assertEqual(exact_date({'date-parts':[[2024,2,29]]}),'2024-02-29')

    def test_first_v1_not_revision(self):
        p = biorxiv_paper([bio(2,'2026-10-01'),bio()],STAMP)
        self.assertEqual(p['date'],'2026-09-01')
        self.assertEqual(p['updated_date'],'2026-10-01')
        self.assertEqual(len(p['versions']),2)
        self.assertEqual(p['related_doi'],'10.1038/s41593-026-12345-x')
        self.assertIsNone(biorxiv_paper([bio(2)],STAMP))
        validate_paper(p)

    def test_abstract_license_gate(self):
        for license in ('cc_by','cc0','cc_by_sa'):
            self.assertIsNotNone(biorxiv_paper([bio(license=license)],STAMP)['abstract'])
        for license in ('cc_by_nc','all_rights_reserved','unknown'):
            self.assertIsNone(biorxiv_paper([bio(license=license)],STAMP)['abstract'])

    def test_stable_journal_and_online_date(self):
        journal = CONFIG['journals'][0]
        row = {'DOI':'10.1038/example','title':['Fixture'],'type':'journal-article', 'ISSN':['0028-0836'],
               'published-online':{'date-parts':[[2026,9,1]]}, 'created':{'date-parts':[[2026,10,1]]},
               'abstract':'Copyrighted abstract'}
        p = crossref_paper(row,journal,STAMP)
        self.assertEqual(p['date'],'2026-09-01')
        self.assertIsNone(p['abstract'])
        self.assertIsNone(crossref_paper({**row,'ISSN':['0000-0000'],'container-title':['Nature']},journal,STAMP))
        self.assertIsNone(crossref_paper({k:v for k,v in row.items() if k!='published-online'},journal,STAMP))

    def test_classification_evidence_and_merged_citations(self):
        topic = {'id':'https://openalex.org/T123','display_name':'Neural circuits','score':0.8,
                 'field':{'id':'https://openalex.org/fields/28'}}
        work = normalize_work({'id':'https://openalex.org/W123','doi':'10.1038/fixture','cited_by_count':0,'topics':[topic]},STAMP)
        p = biorxiv_paper([bio()],STAMP)
        attach_openalex(p,work,CONFIG)
        self.assertEqual(p['citations']['value'],0)
        self.assertEqual(p['citations']['work_id'],'https://openalex.org/W123')
        self.assertEqual(p['date'],'2026-09-01')
        p.update(kind='published',journal_id='nature')
        self.assertTrue(attach_openalex(p,work,CONFIG))
        self.assertEqual(p['classification']['evidence'],['https://openalex.org/T123'])
        p['topics']=[]
        self.assertFalse(attach_openalex(p,None,CONFIG))
        self.assertIsNone(metric()['value'])
        for v in (-1,True,1.2):
            with self.assertRaises(ValueError): metric(v)


class RefreshTests(unittest.TestCase):
    def test_daily_alias_updates_use_canonical_doi(self):
        alias='10.64898/preprint';canonical='10.1038/published'
        old=normalize_work({'id':'https://openalex.org/W123','doi':canonical,'cited_by_count':1,'topics':[]},'2026-10-09T12:00:00Z')
        cache={alias:old}
        topic={'id':'https://openalex.org/T123','display_name':'New topic','score':.9,'field':{'id':'https://openalex.org/fields/28'}}
        class FakeClient:
            def get(self,url):
                self_test.assertIn('10.1038%2Fpublished',url)
                return {'results':[{'id':'https://openalex.org/W123','doi':canonical,'cited_by_count':8,'topics':[topic]}]}
        self_test=self;report={'rows':0}
        refresh_openalex(FakeClient(),[alias],cache,STAMP,report)
        self.assertEqual(cache[alias]['citations']['value'],8)
        self.assertEqual(cache[alias]['topics'][0]['name'],'New topic')
        self.assertEqual(cache[alias]['citations']['observed_at'],STAMP)
        self.assertEqual(report['unmatched'],0)

    def test_singleton_404_is_retried_after_indexing_delay(self):
        identifier='10.64898/alias';cache={}
        class FakeClient:
            def __init__(self,indexed=False): self.indexed=indexed;self.singletons=0
            def get(self,url):
                if '/works?' in url:return {'results':[]}
                self.singletons+=1
                return {'id':'https://openalex.org/W456','doi':'10.1038/canonical','cited_by_count':5,'topics':[]} if self.indexed else {'_not_found':True}
        first=FakeClient();refresh_openalex(first,[identifier],cache,'2026-10-01T12:00:00Z',{'rows':0})
        self.assertTrue(cache[identifier]['_not_found']);self.assertEqual(first.singletons,1)
        early=FakeClient(True);refresh_openalex(early,[identifier],cache,'2026-10-02T12:00:00Z',{'rows':0})
        self.assertEqual(early.singletons,0)
        later=FakeClient(True);refresh_openalex(later,[identifier],cache,'2026-10-09T12:00:00Z',{'rows':0})
        self.assertEqual(later.singletons,1);self.assertEqual(cache[identifier]['citations']['value'],5)

    def test_actual_biorxiv_page_size(self):
        rows=[{**bio(),'doi':f'10.64898/fixture.{i}'} for i in range(4)]
        class FakeClient:
            def __init__(self): self.urls=[]
            def get(self,url):
                self.urls.append(url)
                return {'messages':[{'status':'ok','total':4}], 'collection':rows[:2] if '/0?' in url else rows[2:]}
        client=FakeClient();state={'preprints':{}};report={'rows':0,'excluded':{}}
        collect_biorxiv(client,'2026-09-01','2026-10-10',state,STAMP,report)
        self.assertEqual(len(state['preprints']),4)
        self.assertIn('/2?',client.urls[1])

    def test_last_good_source_data_survives_failure(self):
        state={'preprints':{'fixture':{'versions':{'1':bio()},'observed_at':STAMP}},
               'published':{},'openalex':{},'sources':{'biorxiv':{'status':'failed','last_success':STAMP}}}
        before=copy.deepcopy(state)
        snapshot=make_snapshot(state,CONFIG,STAMP,'2025-10-10','2026-10-10')
        self.assertEqual(snapshot['coverage']['preprints'],1)
        self.assertEqual(snapshot['papers'][0]['metadata_observed_at'],STAMP)
        self.assertEqual(snapshot['sources'][0]['status'],'failed')
        self.assertEqual(state,before)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'good.json';atomic_bytes(target,b'last-good')
            with self.assertRaises(TypeError): atomic_bytes(target,None)
            self.assertEqual(target.read_bytes(),b'last-good')

    def test_http_retries_respect_retry_after_and_restricted_hosts(self):
        self.assertEqual(retry_delay('15',0),15)
        self.assertEqual(retry_delay('Sat, 10 Oct 2026 12:01:00 GMT',0,datetime(2026,10,10,12,tzinfo=timezone.utc)),60)
        waits=[];count=0
        def opener(request,timeout):
            nonlocal count
            count+=1
            if count==1: raise urllib.error.HTTPError(request.full_url,429,'Limited',{'Retry-After':'12'},None)
            return io.BytesIO(b'{"ok":true}')
        client=Client(opener=opener,sleeper=waits.append,clock=lambda:100)
        self.assertTrue(client.get('https://api.crossref.org/works')['ok'])
        self.assertIn(12,waits)
        with self.assertRaises(SourceError): client.get('https://www.nature.com/articles/fixture/metrics')
        def limited(request,timeout): raise urllib.error.HTTPError(request.full_url,429,'Limited',{'Retry-After':'600'},None)
        with self.assertRaises(SourceError): Client(opener=limited,sleeper=lambda _:self.fail('must defer')).get('https://api.openalex.org/works')

    def test_deadline_defers_retry_instead_of_losing_the_checkpoint_window(self):
        calls=[]
        def opener(request,timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url,429,'Limited',{'Retry-After':'12'},None)
        client=Client(opener=opener,sleeper=lambda _:self.fail('must defer'),clock=lambda:0,max_elapsed=40)
        with self.assertRaisesRegex(SourceError,'time budget'):
            client.get('https://api.crossref.org/works')
        self.assertEqual(len(calls),1)

    def test_deadline_persists_successful_partial_records_and_previous_records(self):
        now=[0]
        stamp=datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
        day=stamp[:10]
        existing={**bio(day=day),'doi':'10.64898/existing'}
        received={**bio(day=day),'doi':'10.64898/received'}
        def opener(request,timeout):
            self.assertEqual(now[0],0)
            now[0]=90
            return io.BytesIO(json.dumps({'messages':[{'status':'ok','total':2}],'collection':[received]}).encode())
        client=Client(opener=opener,sleeper=lambda _:self.fail('must defer'),clock=lambda:now[0],max_elapsed=100)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config').mkdir();(root/'data').mkdir()
            (root/'config/sources.json').write_text(json.dumps(CONFIG))
            state={'version':1,'preprints':{existing['doi']:{'versions':{'1':existing},'observed_at':stamp}},
                   'published':{},'openalex':{},'sources':{}}
            (root/'data/state.json.gz').write_bytes(gzip.compress(json.dumps(state).encode()))
            snapshot=run('metadata',root,client)
            self.assertEqual({p['id'] for p in snapshot['papers']},{existing['doi'],received['doi']})
            report=next(s for s in snapshot['sources'] if s['id']=='biorxiv')
            self.assertEqual(report['status'],'partial')
            self.assertIn('time budget',report['errors'][0])
            saved=json.loads(gzip.decompress((root/'data/state.json.gz').read_bytes()))
            self.assertIn(received['doi'],saved['preprints'])
            self.assertEqual(json.loads((root/'public/data/papers.json').read_text())['coverage']['preprints'],2)


class ReadershipTests(unittest.TestCase):
    def test_import_permissions_and_zero(self):
        provider={'id':'fixture','name':'Fixture source','enabled':True,'redistribution_allowed':True,'permission_url':'https://example.org/permission'}
        row={'provider':'fixture','doi':'10.1234/fixture','observed_at':'2020-01-01T00:00:00Z','value':0,'definition':'Declared article views','aggregation':'cumulative'}
        self.assertEqual(validate_import(row,[provider])['value'],0)
        with self.assertRaises(ValueError): validate_import(row,[])
        with self.assertRaises(ValueError): validate_import({**row,'value':True},[provider])
        with self.assertRaises(ValueError): validate_import({**row,'aggregation':'window'},[provider])
        with self.assertRaises(ValueError): ApprovedReadershipQueue({**provider,'enabled':False},lambda _:None)
        later={**row,'observed_at':'2020-01-02T00:00:00Z','value':3}
        self.assertEqual(validated_imports([row,later,row],[provider])[row['doi']]['value'],3)
        with self.assertRaises(ValueError): validate_import({**row,'value':None},[provider])


if __name__=='__main__': unittest.main()
