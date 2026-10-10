import copy
import unittest

from adapters.biorxiv_monthly import MonthlyLedger


class MonthlyReadershipTests(unittest.TestCase):
    def test_raw_monthly_events_replace_revisions_without_double_counting(self):
        ledger=MonthlyLedger();identifier='10.64898/TEST-FIXTURE'
        ledger.apply(identifier,[{'month':'2026-08','fulltext':10,'pdf':3},{'month':'2026-09','fulltext':4,'pdf':5}],
                     '2026-10-01T00:00:00Z',scope='all_versions')
        self.assertEqual(ledger.summary(identifier)['value'],22)
        ledger.apply(identifier,[{'month':'2026-09','fulltext':6,'pdf':5}], '2026-10-02T00:00:00Z',scope='all_versions')
        self.assertEqual(ledger.summary(identifier)['value'],24)
        self.assertFalse(ledger.summary(identifier)['daily_events_inferred'])

    def test_zero_and_missing_channels_are_distinct(self):
        ledger=MonthlyLedger();identifier='10.1101/TEST-FIXTURE'
        self.assertIsNone(ledger.summary(identifier)['value'])
        ledger.apply(identifier,[{'month':'2026-09','fulltext':0,'pdf':0}], '2026-10-01T00:00:00Z',scope='all_versions')
        self.assertEqual(ledger.summary(identifier)['value'],0)
        ledger.apply(identifier,[{'month':'2026-09','fulltext':0,'pdf':None}], '2026-10-02T00:00:00Z',scope='all_versions')
        self.assertIsNone(ledger.summary(identifier)['value'])

    def test_bad_response_retains_last_good_and_version_rows_are_rejected(self):
        ledger=MonthlyLedger();identifier='10.1101/TEST-FIXTURE'
        ledger.apply(identifier,[{'month':'2026-09','fulltext':7,'pdf':2}], '2026-10-01T00:00:00Z',scope='all_versions')
        before=copy.deepcopy(ledger.records)
        for rows in ([{'month':'September','fulltext':3,'pdf':2}], [{'month':'2026-11','fulltext':3,'pdf':2}],
                     [{'month':'2026-09','fulltext':True,'pdf':2}]):
            with self.assertRaises(ValueError):ledger.apply(identifier,rows,'2026-10-02T00:00:00Z',scope='all_versions')
        self.assertEqual(ledger.records,before)
        with self.assertRaises(ValueError):ledger.apply(identifier,[], '2026-10-02T00:00:00Z',scope='version_2')


if __name__=='__main__':unittest.main()
