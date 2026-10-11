import copy
import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from adapters.nature_article import article_doi, article_url, parse_count, parse_html
from ingest.model import crossref_paper, normalize_work, validate_snapshot
from ingest.nature_import import import_file, import_records, read_records, validate_authorization, validate_measurement
from ingest.refresh import make_snapshot

CONFIG=json.loads((Path(__file__).parents[1]/'config/sources.json').read_text())
DOI='10.1038/s41593-026-fixture'
JOURNAL=next(j for j in CONFIG['journals'] if j['id']=='nature-neuroscience')
HASH='a'*64
NOW=datetime.now(timezone.utc).replace(microsecond=0)
def stamp(hours=0):return (NOW-timedelta(hours=hours)).isoformat().replace('+00:00','Z')


def auth():
    return {'permission_url':'https://example.org/permission/TEST-FIXTURE','permission_basis':'TEST FIXTURE — explicit permission for numerical collection and public redistribution.',
            'license':'LicenseRef-ExplicitPermission','verified_at':stamp(3),'journal_ids':['nature-neuroscience'],
            'collection_allowed':True,'redistribution_allowed':True}


def row(count='1.2k',hours=2):
    return {'doi':DOI,'journal_id':'nature-neuroscience','accesses':count,'observed_at':stamp(hours),'source_url':article_url(DOI)}


def state():
    today=NOW.date()
    p=crossref_paper({'DOI':DOI,'title':['TEST FIXTURE — Nature import'],'type':'journal-article','ISSN':['1097-6256'],
        'published-online':{'date-parts':[[today.year,today.month,today.day]]},'author':[{'given':'TEST','family':'FIXTURE'}]},JOURNAL,stamp(3))
    work=normalize_work({'id':'https://openalex.org/W123','doi':DOI,'cited_by_count':7,'topics':[]},stamp(3))
    return {'version':1,'preprints':{},'published':{DOI:p},'openalex':{DOI:work},'sources':{}}


def html(count='1.2k',identifier=DOI,wrapper=True):
    counter=f'<p class="extra c-article-metrics-bar__count">{count}<span> Accesses</span></p>'
    counter=f'<div class="c-article-metrics-bar__wrapper">{counter}<p class="c-article-metrics-bar__count">99 Citations</p></div>' if wrapper else counter
    return f'<meta name="citation_doi" content="{identifier}"><link rel="canonical" href="{article_url(identifier)}">{counter}<p>TEST FIXTURE text must never be stored.</p>'


class NatureParserTests(unittest.TestCase):
    def test_exact_zero_missing_and_rounded_k_m_are_distinct(self):
        for value,expected,approximate in [(0,0,False),('1,234',1234,False),('1\u202f234',1234,False),('1.2k',1200,True),('2.3M',2300000,True),('1.001k',1001,True),('0k',0,True)]:
            with self.subTest(value=value):
                parsed=parse_count(value);self.assertEqual((parsed['value'],parsed['approximate']),(expected,approximate))
        for missing in (None,'','—','N/A'):
            self.assertIsNone(parse_count(missing)['value'])

    def test_malformed_or_unsafe_counts_are_rejected(self):
        for value in (True,-1,1.2,'1,2k','1.2','NaN','1e3','2 million','12,34','0.0001k',str(2**53),{'value':12}):
            with self.subTest(value=value),self.assertRaises(ValueError):parse_count(value)

    def test_canonical_article_mapping_covers_modern_and_legacy_dois(self):
        for value in (DOI,'10.1038/nature12345','10.1038/nn.1234','10.1038/nmeth.1234','10.1038/ncomms1234'):
            self.assertEqual(article_doi(article_url(value)),value)
        self.assertEqual(article_doi('https://nature.com/articles/S41593-026-FIXTURE/?utm_source=test'),DOI)
        self.assertEqual(article_url('https://doi.org/'+DOI.upper()),article_url(DOI))
        for url in ('http://www.nature.com/articles/foo','https://evil.example/articles/foo','https://www.nature.com/search?q=foo',article_url(DOI)+'/metrics','https://user:secret@www.nature.com/articles/foo','https://www.nature.com/articles/a%2Fb'):
            with self.subTest(url=url),self.assertRaises(ValueError):article_doi(url)

    def test_html_bar_identity_missing_and_no_expressive_text_or_other_metrics(self):
        parsed=parse_html(html(),DOI,article_url(DOI));self.assertEqual(parsed['value'],1200);self.assertTrue(parsed['approximate'])
        self.assertNotIn('text',parsed);self.assertNotIn('citations',parsed)
        self.assertIsNone(parse_html(html(wrapper=False))['value'])
        self.assertIsNone(parse_html(html('—'))['value'])
        self.assertEqual(parse_html(html('0'))['value'],0)
        self.assertEqual(parse_html(html()+html())['value'],1200)

    def test_html_conflicts_malformed_counters_and_unclosed_bars_are_rejected(self):
        for body in (html()+html('2k'),html('garbage'),html().replace('</div>',''),html().replace(DOI,'10.1038/different',1),'no identifying metadata'):
            with self.subTest(body=body),self.assertRaises(ValueError):parse_html(body,DOI)


class NatureImportTests(unittest.TestCase):
    def test_permission_scope_and_source_timestamps_are_required(self):
        for change in ({'redistribution_allowed':False},{'collection_allowed':False},{'license':'all-rights-reserved'},
                       {'permission_url':'https://www.nature.com/info/additional-terms'},{'permission_url':'https://example.org/permission?token=secret'},
                       {'verified_at':'2999-01-01T00:00:00Z'},{'journal_ids':['plos-one']}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_authorization({**auth(),**change},stamp())
        for change in ({'observed_at':'2999-01-01T00:00:00Z'},{'source_updated_at':stamp(1)},
                       {'journal_id':'nature'},{'doi':'10.1038/unknown'},{'source_url':article_url(DOI)+'/metrics'},
                       {'source_label':'Citations'},{'abstract':'TEST FIXTURE unlicensed text'}):
            with self.subTest(change=change),self.assertRaises(ValueError):import_records(state(),CONFIG,[{**row(),**change}],auth(),'json',HASH,stamp())

    def test_updates_same_doi_retain_missing_and_older_measurements_without_summing(self):
        s=state();import_records(s,CONFIG,[row()],auth(),'json',HASH,stamp())
        before=copy.deepcopy(s['nature_readership'][DOI])
        report=import_records(s,CONFIG,[row(None,1)],auth(),'csv',HASH,stamp())
        self.assertEqual(s['nature_readership'][DOI],before);self.assertEqual(report['missing_retained'],1)
        report=import_records(s,CONFIG,[row(9000,3)],auth(),'json',HASH,stamp())
        self.assertEqual(s['nature_readership'][DOI],before);self.assertEqual(report['older_ignored'],1)
        import_records(s,CONFIG,[row(0,1)],auth(),'csv',HASH,stamp())
        self.assertEqual(s['nature_readership'][DOI]['value'],0)
        self.assertEqual(s['nature_readership'][DOI]['observed_at'],stamp(1))

    def test_invalid_batch_and_same_timestamp_conflicts_change_no_state(self):
        s=state();import_records(s,CONFIG,[row()],auth(),'json',HASH,stamp());before=copy.deepcopy(s)
        for rows in ([row(2000,1),{**row(),'doi':'10.1038/unknown'}],[row(1300,2)]):
            with self.assertRaises(ValueError):import_records(s,CONFIG,rows,auth(),'json',HASH,stamp())
            self.assertEqual(s,before)

    def test_snapshot_keeps_official_dates_citations_and_authorization_provenance(self):
        s=state();original=copy.deepcopy(s['published'][DOI]);import_records(s,CONFIG,[row()],auth(),'html',HASH,stamp())
        snapshot=make_snapshot(s,CONFIG,stamp(),(NOW.date()-timedelta(days=365)).isoformat(),NOW.date().isoformat())
        validate_snapshot(snapshot,CONFIG)
        p=snapshot['papers'][0]
        self.assertEqual(p['date'],original['date']);self.assertEqual(p['title'],original['title']);self.assertEqual(p['citations']['value'],7)
        self.assertEqual(p['accesses']['value'],1200);self.assertTrue(p['accesses']['approximate'])
        self.assertEqual(p['accesses']['source_updated_at'],None);self.assertNotEqual(p['accesses']['imported_at'],p['accesses']['observed_at'])
        imported_sources=[source for source in p['provenance'] if source['source']=='Nature authorized offline import']
        self.assertEqual(len(imported_sources),2)
        self.assertTrue(all(source['license']=='LicenseRef-ExplicitPermission' for source in imported_sources))
        self.assertEqual(snapshot['readership']['nature']['measured'],1);self.assertFalse(snapshot['readership']['nature']['live_fetch_enabled'])
        broken={**p['accesses'],'approximate':False}
        with self.assertRaises(ValueError):validate_measurement(broken,DOI,'nature-neuroscience',stamp())

    def test_csv_json_html_inputs_and_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'facts.csv'
            path.write_text('doi,journal_id,accesses,observed_at\n'+DOI+',nature-neuroscience,1.2k,'+stamp(2)+'\n')
            rows,fingerprint=read_records(path,'csv');self.assertEqual(rows[0]['accesses'],'1.2k');self.assertEqual(len(fingerprint),64)
            path.write_text('doi,doi\n'+DOI+','+DOI+'\n')
            with self.assertRaises(ValueError):read_records(path,'csv')
            path.write_text(json.dumps({'schema_version':1,'records':[row()]}));self.assertEqual(read_records(path,'json')[0],[row()])
            path.write_text(html());rows,_=read_records(path,'html',{'journal_id':'nature-neuroscience','observed_at':stamp(2)})
            self.assertEqual(rows[0]['doi'],DOI);self.assertEqual(rows[0]['accesses'],'1.2k')

    def test_file_import_is_offline_atomic_and_recovers_after_bad_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config').mkdir();(root/'data').mkdir()
            (root/'config/sources.json').write_text(json.dumps(CONFIG))
            (root/'data/state.json.gz').write_bytes(gzip.compress(json.dumps(state()).encode()))
            path=root/'facts.json';permission=root/'permission.json';path.write_text(json.dumps([row()]));permission.write_text(json.dumps(auth()))
            with patch('urllib.request.urlopen',side_effect=AssertionError('Offline imports must not fetch anything')):
                import_file(root,path,permission)
                outputs=[root/'data/state.json.gz',root/'public/data/papers.json',root/'data/coverage.json']
                before=[p.read_bytes() for p in outputs]
                path.write_text(json.dumps([row(2000,1),{**row(),'doi':'10.1038/unknown'}]))
                with self.assertRaises(ValueError):import_file(root,path,permission)
                self.assertEqual([p.read_bytes() for p in outputs],before)
                path.write_text(json.dumps([row(0,1)]));import_file(root,path,permission)
                self.assertEqual(json.loads(outputs[1].read_text())['papers'][0]['accesses']['value'],0)
                saved=json.loads(gzip.decompress(outputs[0].read_bytes()))
                self.assertNotIn('HTML',json.dumps(saved));self.assertEqual(len(saved['nature_readership']),1)

    def test_live_fetch_or_missing_authorization_cannot_activate_the_module(self):
        s=state()
        with self.assertRaises(ValueError):import_records(s,{**CONFIG,'nature_import':{'enabled':True,'live_fetch_enabled':True}},[row()],auth(),'json',HASH,stamp())
        with self.assertRaises(ValueError):import_records(s,CONFIG,[row()],{},'json',HASH,stamp())
        self.assertNotIn('nature_readership',s)


if __name__=='__main__':unittest.main()
