from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from inventory.models import StockHed, StockDtl

from .transaction_posting import (
    _inward_item_inventory_postings,
    post_inward_to_inventory,
    reverse_inward_from_inventory,
)


class _Lines:
    def __init__(self, *lines):
        self._lines = lines

    def select_related(self, *_fields):
        return list(self._lines)


class InwardInventoryPostingTests(SimpleTestCase):
    def _objects(self, *, quantity='20', sample_qty='0'):
        item = SimpleNamespace(
            pk=34,
            item_category_id='RM',
            sample_qty=Decimal(sample_qty),
        )
        line = SimpleNamespace(
            item=item,
            item_id=item.pk,
            quantity=Decimal(quantity),
        )
        inward = SimpleNamespace(
            pk=9,
            customer_id=8,
            inward_dt=date(2026, 9, 12),
            lines=_Lines(line),
        )
        return line, inward

    def test_item_quantity_posts_once_without_batch(self):
        line, inward = self._objects(quantity='20', sample_qty='0')

        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('20.000'))],
        )

    def test_sample_quantity_is_deducted_from_item_total(self):
        line, inward = self._objects(quantity='20', sample_qty='0.250')

        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('19.750'))],
        )

    @patch('inventory.transaction_posting.reverse_inward_ledger')
    @patch('inventory.transaction_posting.post_inward_ledger')
    @patch('inventory.transaction_posting.inventory_apply_batch_delta')
    def test_post_and_reverse_use_the_same_unbatched_bucket(self, apply_delta, mock_post, mock_rev):
        _line, inward = self._objects(quantity='20', sample_qty='0')

        post_inward_to_inventory(inward)
        reverse_inward_from_inventory(inward)

        self.assertEqual(apply_delta.call_count, 2)
        posted, reversed_call = apply_delta.call_args_list
        self.assertEqual(posted.kwargs['batch_no'], '')
        self.assertIsNone(posted.kwargs['mfg_date'])
        self.assertIsNone(posted.kwargs['exp_date'])
        self.assertEqual(posted.kwargs['qty_delta'], Decimal('20.000'))
        self.assertEqual(reversed_call.kwargs['batch_no'], '')
        self.assertEqual(reversed_call.kwargs['qty_delta'], Decimal('-20.000'))

    def test_conversion_factor_multiplies_inward_quantity(self):
        # 1 kg inward with conversion factor 1000 -> 1000 grams in inventory
        item = SimpleNamespace(
            pk=35,
            item_category_id='RM',
            sample_qty=Decimal('0'),
            conversion_factor=Decimal('1000.0000'),
        )
        line = SimpleNamespace(
            item=item,
            item_id=item.pk,
            quantity=Decimal('1.000'),
        )
        inward = SimpleNamespace(
            pk=10,
            customer_id=8,
            inward_dt=date(2026, 9, 12),
            lines=_Lines(line),
        )
        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('1000.000'))],
        )

    def test_conversion_factor_with_sample_qty(self):
        # 2 kg inward with 0.1 kg sample -> 1.9 kg net * 1000 = 1900 grams
        item = SimpleNamespace(
            pk=36,
            item_category_id='RM',
            sample_qty=Decimal('0.100'),
            conversion_factor=Decimal('1000.0000'),
        )
        line = SimpleNamespace(
            item=item,
            item_id=item.pk,
            quantity=Decimal('2.000'),
        )
        inward = SimpleNamespace(
            pk=11,
            customer_id=8,
            inward_dt=date(2026, 9, 12),
            lines=_Lines(line),
        )
        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('1900.000'))],
        )


class InventoryStockLifecycleAjaxTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        from masters.models import FinancialYear, MstCust, MstItem, MstProdCat, MstState, MstItemType, MstUom
        from inventory.models import StockHed, StockDtl

        User = get_user_model()
        self.user = User.objects.create_user(
            username='inv_test_user',
            password='Password123!',
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.fy = FinancialYear.objects.create(
            fy_start_year=2026,
            fy_end_year=2027,
            fy_display='2026-27',
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            is_current=True,
            is_open=True,
        )
        self.state = MstState.objects.create(state_name='Maharashtra', gst_code='27')
        self.cust = MstCust.objects.create(cust_id=1, cust_name='Test Cust', short_name='TC', state=self.state)
        self.cat = MstProdCat.objects.create(prod_cat_id='RM', prod_cat_name='Raw Materials')
        self.uom = MstUom.objects.create(uom_name='Kilogram', short_name='kg')
        self.item_type = MstItemType.objects.create(item_category=self.cat, item_type_name='Raw Material')
        self.item = MstItem.objects.create(
            item_name='Chemical A',
            item_category=self.cat,
            item_type=self.item_type,
            uom=self.uom,
        )

        self.hed = StockHed.objects.create(
            financial_year=self.fy,
            customer=self.cust,
            item=self.item,
            item_category=self.cat,
            op_date=date(2026, 4, 1),
            opn_qty=Decimal('0.000'),
            rcpt_qty=Decimal('50.000'),
            issue_qty=Decimal('30.000'),
            closing_qty=Decimal('20.000'),
        )

        # Movement 1: Inward on 2026-05-10 (+50)
        StockDtl.objects.create(
            stock=self.hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='1',
            trn_date=date(2026, 5, 10),
            quantity=Decimal('50.000'),
            source_line_id='INW-1-1',
        )

        # Movement 2: Dispense on 2026-06-15 (-30)
        StockDtl.objects.create(
            stock=self.hed,
            tran_id=StockDtl.TRAN_DIS,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no='2',
            trn_date=date(2026, 6, 15),
            quantity=Decimal('30.000'),
            source_line_id='DIS-2-1',
        )

    def test_missing_inv_id_returns_400(self):
        from django.urls import reverse
        resp = self.client.get(reverse('inventory:inventory_stock_lifecycle_ajax'))
        self.assertEqual(resp.status_code, 400)

    def test_all_time_lifecycle(self):
        from django.urls import reverse
        resp = self.client.get(
            reverse('inventory:inventory_stock_lifecycle_ajax'),
            {'inv_id': self.hed.stock_lnkno},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['all_time_events_count'], 2)
        self.assertEqual(len(data['events']), 2)
        self.assertFalse(data['is_periodic'])

    def test_periodic_lifecycle_filter(self):
        from django.urls import reverse
        # Filter for June only: Movement 1 (May) is prior -> opening bal 50. Movement 2 (June) is in-period -> issue 30.
        resp = self.client.get(
            reverse('inventory:inventory_stock_lifecycle_ajax'),
            {
                'inv_id': self.hed.stock_lnkno,
                'from_date': '2026-06-01',
                'to_date': '2026-06-30',
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['is_periodic'])
        self.assertEqual(data['period_opening_bal'], '50.000')
        self.assertEqual(data['period_rcpt_qty'], '0.000')
        self.assertEqual(data['period_issue_qty'], '30.000')
        self.assertEqual(data['period_closing_bal'], '20.000')
        self.assertEqual(data['period_net_change'], '-30.000')
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['doc_id'], '2')

    def test_stock_movement_reversal_consolidation(self):
        """
        Verify that multiple reversal/post pairs from document edits are consolidated
        into net amendment events (+delta in green, -delta in red) and that zero-delta
        edits are completely suppressed.
        """
        from datetime import datetime
        from django.utils import timezone
        from django.urls import reverse

        from masters.models import MstItem
        item2 = MstItem.objects.create(
            item_name='Chemical B',
            item_category=self.cat,
            item_type=self.item_type,
            uom=self.uom,
        )

        # Create a new StockHed
        hed = StockHed.objects.create(
            financial_year=self.fy,
            customer=self.cust,
            item=item2,
            item_category=self.cat,
            op_date=date(2026, 4, 1),
            batch_no='BATCH-CONSOLIDATE-TEST',
            opn_qty=Decimal('0.000'),
            rcpt_qty=Decimal('29.500'),
            issue_qty=Decimal('0.000'),
            closing_qty=Decimal('29.500'),
        )

        base_t = timezone.now()

        # Step 1: Initial inward of 29.500 kg (Main record)
        m1 = StockDtl.objects.create(
            stock=hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='INW-100',
            trn_date=date(2026, 9, 1),
            quantity=Decimal('29.500'),
            is_reversal=False,
            source_line_id='INW-100-1',
        )
        StockDtl.objects.filter(pk=m1.pk).update(created_at=base_t - timedelta(days=2))

        # Step 2: User edits Inward, changing qty from 29.500 to 30.500 (+1.000 kg)
        t_edit1 = base_t - timedelta(days=1)
        m2_rev = StockDtl.objects.create(
            stock=hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='INW-100',
            trn_date=date(2026, 9, 1),
            quantity=Decimal('29.500'),
            is_reversal=True,
            source_line_id='INW-100-REV1',
        )
        m2_post = StockDtl.objects.create(
            stock=hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='INW-100',
            trn_date=date(2026, 9, 1),
            quantity=Decimal('30.500'),
            is_reversal=False,
            source_line_id='INW-100-POST1',
        )
        StockDtl.objects.filter(pk__in=[m2_rev.pk, m2_post.pk]).update(created_at=t_edit1)

        # Step 3: User edits Inward metadata only (qty unchanged: 30.500 -> 30.500)
        t_edit2 = base_t - timedelta(hours=12)
        m3_rev = StockDtl.objects.create(
            stock=hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='INW-100',
            trn_date=date(2026, 9, 1),
            quantity=Decimal('30.500'),
            is_reversal=True,
            source_line_id='INW-100-REV2',
        )
        m3_post = StockDtl.objects.create(
            stock=hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='INW-100',
            trn_date=date(2026, 9, 1),
            quantity=Decimal('30.500'),
            is_reversal=False,
            source_line_id='INW-100-POST2',
        )
        StockDtl.objects.filter(pk__in=[m3_rev.pk, m3_post.pk]).update(created_at=t_edit2)

        # Step 4: User edits Inward, reducing qty from 30.500 to 28.500 (-2.000 kg)
        t_edit3 = base_t - timedelta(hours=2)
        m4_rev = StockDtl.objects.create(
            stock=hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='INW-100',
            trn_date=date(2026, 9, 1),
            quantity=Decimal('30.500'),
            is_reversal=True,
            source_line_id='INW-100-REV3',
        )
        m4_post = StockDtl.objects.create(
            stock=hed,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='INW-100',
            trn_date=date(2026, 9, 1),
            quantity=Decimal('28.500'),
            is_reversal=False,
            source_line_id='INW-100-POST3',
        )
        StockDtl.objects.filter(pk__in=[m4_rev.pk, m4_post.pk]).update(created_at=t_edit3)

        # Update hed receipt quantity to match the final net state
        hed.rcpt_qty = Decimal('28.500')
        hed.save()

        # Query lifecycle AJAX
        resp = self.client.get(
            reverse('inventory:inventory_stock_lifecycle_ajax'),
            {'inv_id': hed.stock_lnkno},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # There are 7 raw StockDtl rows, but they must be consolidated into exactly 3 meaningful events:
        # Event 1: Initial inward +29.500 (Main Record)
        # Event 2: Edit 1 +1.000 (Qty Amendment)
        # (Edit 2 zero-delta suppressed!)
        # Event 3: Edit 3 -2.000 (Qty Amendment)
        self.assertEqual(data['all_time_events_count'], 3)
        self.assertEqual(len(data['events']), 3)

        ev1 = data['events'][0]
        self.assertEqual(ev1['label'], 'Inward RM/PM')
        self.assertEqual(ev1['qty_delta'], '29.500')
        self.assertEqual(ev1['balance_after'], '29.500')

        ev2 = data['events'][1]
        self.assertEqual(ev2['label'], 'Inward RM/PM (Qty Amendment)')
        self.assertEqual(ev2['qty_delta'], '1.000')
        self.assertEqual(ev2['balance_after'], '30.500')
        self.assertIn('from 29.500 to 30.500', ev2['detail'])

        ev3 = data['events'][2]
        self.assertEqual(ev3['label'], 'Inward RM/PM (Qty Amendment)')
        self.assertEqual(ev3['qty_delta'], '-2.000')
        self.assertEqual(ev3['balance_after'], '28.500')
        self.assertIn('from 30.500 to 28.500', ev3['detail'])

        self.assertTrue(data['balance_matches_ledger'])
        self.assertEqual(data['computed_balance'], '28.500')
        self.assertEqual(data['ledger_qty'], '28.500')

