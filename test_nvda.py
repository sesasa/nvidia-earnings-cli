import unittest
from unittest.mock import patch
import nvda


class FinancialTests(unittest.TestCase):
    def setUp(self):
        self.db = nvda.connect(':memory:')
        self.filing = {'accession': 'test', 'form': '10-Q', 'report_date': '2026-07-26',
                       'filed': '2026-08-26', 'url': 'https://example.com/filing'}
        self.db.execute('INSERT INTO filings VALUES(?,?,?,?,?)', tuple(self.filing.values()))

    def tearDown(self):
        self.db.close()

    def fact(self, tag, value, start='2026-04-27', end='2026-07-26', accession='test'):
        self.db.execute('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        ('us-gaap', tag, 'USD', start, end, value, accession, '2026-08-26', '10-Q', 2027, 'Q2'))

    def test_quarter_income_excludes_ytd_and_other_accessions(self):
        tag = nvda.METRICS['income']['revenue'][0]
        self.fact(tag, 100)
        self.fact(tag, 180, '2026-01-26')
        self.fact(tag, 999, accession='unrelated')
        self.assertEqual(nvda.statement(self.db, self.filing, 'income')['revenue']['value'], 100)

    def test_cashflow_is_labeled_ytd_and_fcf_correct(self):
        self.fact('NetCashProvidedByUsedInOperatingActivities', 80e9, '2026-01-26')
        self.fact('PaymentsToAcquirePropertyPlantAndEquipment', 5e9, '2026-01-26')
        result = nvda.answer(self.db, 'What is free cash flow?')
        self.assertIn('$75.000 billion', result)
        self.assertIn('year to date', result)

    def test_mismatched_cashflow_periods_rejected(self):
        self.fact('NetCashProvidedByUsedInOperatingActivities', 80, '2026-01-26')
        self.fact('PaymentsToAcquirePropertyPlantAndEquipment', 5)
        self.assertIn('periods or units do not match', nvda.answer(self.db, 'free cash flow'))

    def test_growth_matches_prior_year_duration(self):
        tag = nvda.METRICS['income']['revenue'][0]
        self.fact(tag, 150)
        self.fact(tag, 100, '2025-04-28', '2025-07-27')
        self.fact(tag, 190, '2025-01-27', '2025-07-27')
        self.assertIn('50.00%', nvda.answer(self.db, 'revenue growth'))

    def test_missing_is_not_zero(self):
        self.assertIn('required figure is missing', nvda.answer(self.db, 'current ratio'))

    def test_productive_assets_fallback_discloses_scope(self):
        self.fact('NetCashProvidedByUsedInOperatingActivities', 80e9, '2026-01-26')
        self.fact('PaymentsToAcquireProductiveAssets', 5e9, '2026-01-26')
        result = nvda.answer(self.db, 'free cash flow')
        self.assertIn('$75.000 billion', result)
        self.assertIn('software and intangible', result)

    def test_document_date_extracted_when_meta_missing(self):
        nvda.store_document(self.db, 'https://example.com', 'Earnings', 'earnings release', '',
                            'August 26, 2026' + ' Earnings material. ' * 20)
        self.assertEqual(self.db.execute('SELECT published FROM documents').fetchone()[0], '2026-08-26')

    def test_zero_denominator(self):
        self.fact('AssetsCurrent', 12, '')
        self.fact('LiabilitiesCurrent', 0, '')
        self.assertIn('denominator is zero', nvda.answer(self.db, 'current ratio'))

    def test_income_annual_not_quarter(self):
        self.filing['form'] = '10-K'
        tag = nvda.METRICS['income']['revenue'][0]
        self.fact(tag, 100)
        self.fact(tag, 400, '2025-07-28')
        result = nvda.statement(self.db, self.filing, 'income')['revenue']
        self.assertEqual(result['value'], 400)
        self.assertIn('full year', nvda.period(result))

    def test_ingest_idempotent_and_preserves_revisions(self):
        recent = {'accessionNumber': ['a'], 'form': ['10-Q'], 'reportDate': ['2026-07-26'],
                  'filingDate': ['2026-08-26'], 'primaryDocument': ['nvda.htm']}
        data = {'cik': 1045810, 'facts': {'us-gaap': {'Assets': {'units': {'USD': [
            {'end': '2026-07-26', 'val': 100, 'accn': 'a'},
            {'end': '2026-07-26', 'val': 101, 'accn': 'b'}]}}}}}
        for _ in range(2):
            nvda.ingest_sec(self.db, {'filings': {'recent': recent}}, data)
        self.assertEqual(self.db.execute('SELECT count(*) FROM facts').fetchone()[0], 2)

    def test_missing_ai_configuration(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
                nvda.answer(self.db, 'why', ai=True)

    def test_html_excludes_scripts_preserves_metadata(self):
        p = nvda.Page('<meta property="og:title" content="Earnings"><p>Revenue &amp; cash</p>'
                      '<script>bad()</script><a href="/news/test">Source</a>')
        self.assertNotIn('bad()', p.text)
        self.assertIn('Revenue & cash', p.text)
        self.assertEqual(p.meta['og:title'], 'Earnings')
        self.assertEqual(p.links, ['/news/test'])


if __name__ == '__main__':
    unittest.main()
