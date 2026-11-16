"""
Tests for the Director Transaction Dashboard views and API endpoints.
"""

from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse


class DashboardViewsTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='director_test',
            password='Password123!',
        )
        self.client = Client()

    def test_unauthenticated_redirects(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_authenticated_dashboard_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Transaction Command Center')

    def test_authenticated_director_dashboard_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('director_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Transaction Command Center')

    def test_api_summary_kpis(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_summary_kpis'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('total_inwards', data)
        self.assertIn('total_grn_rm', data)
        self.assertIn('total_grn_pm', data)
        self.assertIn('total_inw_rm_qty', data)
        self.assertIn('total_inw_pm_qty', data)
        self.assertIn('total_dpr', data)
        self.assertIn('total_logsheets', data)
        self.assertIn('total_packaging_entries', data)
        self.assertIn('total_shippers', data)
        self.assertIn('total_packed_nos', data)
        self.assertIn('total_sales_orders', data)
        self.assertIn('total_order_val', data)
        self.assertIn('total_sales_invoices', data)
        self.assertIn('total_invoice_amount', data)
        self.assertIn('total_rm_dispensings', data)

    def test_api_inward_logsheet(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_inward_logsheet'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)
        self.assertIn('total_rm_qty', data)
        self.assertIn('total_pm_qty', data)
        self.assertIn('total_rm_lines', data)
        self.assertIn('total_pm_lines', data)
        self.assertIn('total_rm_count', data)
        self.assertIn('total_pm_count', data)

    def test_api_granulation_logsheet(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_granulation_logsheet'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_api_dpr_report(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_dpr_report'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_api_rm_dispensing(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_rm_dispensing'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_api_packing_report(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_packing_report'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_api_sales_orders(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_sales_orders'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_api_sales_summary(self):
        self.client.force_login(self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('dashboard_sales_summary'), {
            'from_date': today,
            'to_date': today,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_api_stock_overview(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard_stock_overview'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)
        self.assertIn('totals', data)
        self.assertIn('RM', data['totals'])
        self.assertIn('PM', data['totals'])
        self.assertIn('FG', data['totals'])
        self.assertIn('ALL', data['totals'])

    def test_api_stock_overview_periodic(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard_stock_overview'), {
            'from_date': '2026-01-01',
            'to_date': '2026-03-31',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('is_periodic'))
        self.assertEqual(data.get('from_date'), '2026-01-01')
        self.assertEqual(data.get('to_date'), '2026-03-31')

    def test_api_custom_date_range(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard_summary_kpis'), {
            'from_date': '2026-01-01',
            'to_date': '2026-12-31',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['from_date'], '2026-01-01')
        self.assertEqual(data['to_date'], '2026-12-31')

    def test_api_all_time_filter(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard_summary_kpis'), {
            'all': '1',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['from_date'], '2000-01-01')
        self.assertEqual(data['to_date'], '2099-12-31')
