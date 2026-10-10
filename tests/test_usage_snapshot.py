import copy
import unittest

from ingest.biorxiv_usage import numeric_snapshot, refresh_reference

COMMIT='a329dc20051d44ff28488f69fc1ac74b11b5a176'
STAMP='2026-10-10T19:00:00Z'


def payload():
    return {'category':'neuroscience','start':'2026-05-01','end':'2026-10-10','updated':'2026-10-10 17:17 UTC',
            'papers':[{'doi':'10.64898/fixture','title':'DO NOT COPY EXPRESSIVE METADATA','first_author':'DO NOT COPY',
                       'date':'2026-01-01','fetched':'2026-10-09','usage':{'2026-05':[20,167],'2026-06':[14,43]}}]}


class UsageSnapshotTests(unittest.TestCase):
    def test_available_months_raw_sum_ignores_titles_and_source_dates(self):
        measurements,report=numeric_snapshot(payload(),COMMIT,STAMP)
        m=measurements['10.64898/fixture']
        self.assertEqual(m['value'],244);self.assertEqual(m['fulltext'],34);self.assertEqual(m['pdf'],210)
        self.assertNotIn('title',m);self.assertNotIn('first_author',m);self.assertNotIn('date',m)
        self.assertEqual(m['upstream_fetched_date'],'2026-10-09');self.assertFalse(m['lifetime_complete'])
        self.assertEqual(report['measured_upstream'],1)

    def test_missing_vs_zero_and_bad_values(self):
        d=payload();d['papers'][0]['usage']=None
        self.assertEqual(numeric_snapshot(d,COMMIT,STAMP)[0],{})
        d['papers'][0]['usage']={'2026-09':[0,0]}
        self.assertEqual(numeric_snapshot(d,COMMIT,STAMP)[0]['10.64898/fixture']['value'],0)
        for usage in ({'2026-09':[True,2]},{'2026-09':[-1,2]},{'2026-09':[1]}, {'September':[1,2]}):
            d['papers'][0]['usage']=usage
            with self.assertRaises(ValueError):numeric_snapshot(d,COMMIT,STAMP)

    def test_invalid_refresh_retains_last_good_and_unchanged_commit_skips_download(self):
        provider={'id':'biorxiv-top-numeric','enabled':True};config={'readership_providers':[provider]}
        state={'sources':{},'reference_readership':{'10.64898/good':{'value':9}}}
        before=copy.deepcopy(state['reference_readership'])
        class BadClient:
            def get(self,url):return {'object':{'sha':COMMIT}} if 'api.github.com' in url else {'papers':[]}
        refresh_reference(BadClient(),state,config);self.assertEqual(state['reference_readership'],before)
        self.assertEqual(state['sources']['biorxiv-top-numeric']['status'],'failed')
        state['readership_source_commit']=COMMIT
        class Unchanged:
            def get(self,url):
                if 'raw.githubusercontent' in url:raise AssertionError('No redundant source download')
                return {'object':{'sha':COMMIT}}
        refresh_reference(Unchanged(),state,config);self.assertEqual(state['reference_readership'],before)


if __name__=='__main__':unittest.main()
