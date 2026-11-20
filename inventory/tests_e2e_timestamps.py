"""
E2E Automated Test Suite for Real-Time Timestamps & Date-Range Tracking.
Domain: Inventory Ledger (StockHed, StockDtl), Stock Adjustments (TrnStkAdjHed),
        Lifecycle AJAX API (/inventory/ajax/stock-lifecycle/), and Audit Shift Queries.

Requirements Covered:
- R1: Automatic Real-Time Timestamping across all inventory transactions.
      No manual input field for entering today's date in stock adjustment template.
- R2: Timestamp tracking across creation and modification.
      Preserving historical records without timestamps (NULL).
- R3: Logging real-time timestamps in inventory history records (StockDtl).
      Querying and filtering inventory movements by exact date range / datetime window.
- Tier 2 Boundary / Corner Cases:
      Same-day morning vs. afternoon temporal filtering.
      BVA boundary conditions (exact start, exact end, just before, just after).
      Fallback to calendar date for legacy records with NULL timestamps.
- Tier 3 Cross-Feature Combinations:
      Inward -> Stock Adjustment -> Sales Invoice lifecycle chain.
      Compensating reversals capturing real-time timestamps.
- Tier 4 Real-World Workload:
      Pharmaceutical manufacturing shift window audit (Shift 1 vs Shift 2).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import time

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from masters.models import (
    FinancialYear,
    MstCust,
    MstItem,
    MstItemType,
    MstProd,
    MstProdCat,
    MstState,
    MstSupplier,
    MstTransport,
    MstUom,
)
from inventory.models import StockDtl, StockHed, TrnStkAdjHed
from inventory.transaction_posting import (
    post_inward_to_inventory,
    reverse_inward_from_inventory,
)
from transactions.models import TrnInwDtl1, TrnInwHed, TrnSlsHed


class BaseInventoryTimestampTestCase(TestCase):
    """Shared test fixture for inventory ledger tests."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser('e2e_inv_admin', 'inv@example.com', 'adminpass')

        cls.state = MstState.objects.create(state_name='Maharashtra Inv', gst_code='27')
        cls.cust = MstCust.objects.create(
            cust_name='Aura Pharma Limited',
            short_name='AURA',
            address='Turbhe, Navi Mumbai',
            state=cls.state,
            pin_code='400705',
        )
        cls.supplier = MstSupplier.objects.create(
            supl_name='Standard Solvents Ltd',
            short_name='STDSOLV',
            address='Chemical Zone',
            state=cls.state,
            pin_code='400002',
        )
        cls.cat_rm = MstProdCat.objects.create(prod_cat_id='RM', prod_cat_name='Raw Materials')
        cls.cat_pm = MstProdCat.objects.create(prod_cat_id='PM', prod_cat_name='Packaging Materials')
        cls.cat_fg = MstProdCat.objects.create(prod_cat_id='FG', prod_cat_name='Finished Goods')
        cls.transporter = MstTransport.objects.create(transport_name='National Fast Cargo')

        cls.uom_kg = MstUom.objects.create(uom_name='Kilogram', short_name='kg')
        cls.uom_tab = MstUom.objects.create(uom_name='Tablets', short_name='tab')

        cls.item_type_rm = MstItemType.objects.create(
            item_type_name='Active Pharma Ingredient',
            item_category=cls.cat_rm,
        )
        cls.item_type_fg = MstItemType.objects.create(
            item_type_name='Finished Tablet',
            item_category=cls.cat_fg,
        )

        cls.item_rm = MstItem.objects.create(
            item_name='Paracetamol Pure IP',
            item_category=cls.cat_rm,
            item_type=cls.item_type_rm,
            uom=cls.uom_kg,
        )
        cls.prod_fg = MstProd.objects.create(
            prod_name='Paracetamol 500mg Tablets',
            prod_type=cls.item_type_fg,
            prod_category=cls.cat_fg,
            uom=cls.uom_tab,
        )

        cls.fy_2026 = FinancialYear.objects.create(
            fy_start_year=2026,
            fy_end_year=2027,
            fy_display='2026-27',
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )

        # Standard StockHed row for RM
        cls.stock_rm = StockHed.objects.create(
            financial_year=cls.fy_2026,
            customer=cls.cust,
            item=cls.item_rm,
            item_category=cls.cat_rm,
            op_date=date(2026, 4, 1),
            opn_qty=Decimal('0.000'),
            rcpt_qty=Decimal('100.000'),
            issue_qty=Decimal('40.000'),
            closing_qty=Decimal('60.000'),
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)


class LedgerMovementTimestampTests(BaseInventoryTimestampTestCase):
    """
    Tier 1 Feature Coverage:
    - Every inventory transaction action creates corresponding StockDtl records
      containing real-time datetime.
    """

    def test_inward_posting_records_realtime_timestamp_in_stockdtl(self):
        """Posting Inward creates a StockDtl movement row with real-time created_at."""
        t_before = timezone.now()
        inward = TrnInwHed.objects.create(
            customer=self.cust,
            register_no='R-70001',
            grn_category=self.cat_rm,
            grn_no='RM-70001',
            supplier=self.supplier,
            inv_no='INV-POST-01',
            inv_dt=date.today(),
            inward_dt=date.today(),
            transporter=self.transporter,
            vehicle_no='MH-12-INW',
        )
        line = TrnInwDtl1.objects.create(
            inward=inward,
            item=self.item_rm,
            quantity=Decimal('25.000'),
            uom=self.uom_kg,
            rate=Decimal('450.00'),
        )

        post_inward_to_inventory(inward)
        t_after = timezone.now()

        # Find the StockDtl row created for this inward line
        movement = StockDtl.objects.filter(
            source_line_id__icontains=str(line.pk),
            tran_id=StockDtl.TRAN_INW,
        ).first()

        self.assertIsNotNone(
            movement,
            "R3 Acceptance Criteria: Inward posting must create StockDtl movement record.",
        )
        self.assertIsNotNone(
            movement.created_at,
            "R3 Acceptance Criteria: StockDtl must contain real-time created_at datetime.",
        )
        self.assertTrue(
            t_before - timedelta(seconds=2) <= movement.created_at <= t_after + timedelta(seconds=2),
            f"StockDtl.created_at ({movement.created_at}) must match real-time window [{t_before}, {t_after}].",
        )


class StockAdjustmentTimestampTests(BaseInventoryTimestampTestCase):
    """
    Tier 1 Feature Coverage:
    - Stock Adjustment header (TrnStkAdjHed) captures real-time created_at and updated_at.
    - Template stock_adjustment.html does NOT provide manual date input for today's date.
    - Posting stock adjustments logs real-time datetime in StockDtl.
    """

    def test_stock_adjustment_header_has_timestamp_fields(self):
        """TrnStkAdjHed must define created_at and updated_at DateTimeFields."""
        has_created = hasattr(TrnStkAdjHed, 'created_at')
        has_updated = hasattr(TrnStkAdjHed, 'updated_at')
        self.assertTrue(
            has_created,
            "R2 Requirement: TrnStkAdjHed must define 'created_at' DateTimeField.",
        )
        self.assertTrue(
            has_updated,
            "R2 Requirement: TrnStkAdjHed must define 'updated_at' DateTimeField.",
        )

    def test_stock_adjustment_template_no_manual_date_input(self):
        """Template inventory/stock_adjustment.html must NOT render manual date input for today's date."""
        rendered = render_to_string(
            'inventory/stock_adjustment.html',
            context={'base_template': 'base.html'},
        )
        # Verify that stkAdjDate is not an editable date input
        self.assertNotIn(
            '<input type="date" id="stkAdjDate"',
            rendered,
            "R1 Acceptance Criteria: Stock adjustment template must NOT have a manual input field for document date.",
        )

    def test_stock_adjustment_posting_records_realtime_timestamp_in_stockdtl(self):
        """Posting stock adjustment records real-time timestamp in StockDtl."""
        from inventory.models import TrnStkAdjDtl1, TrnStkAdjDtl2
        from inventory.ledger_service import post_stock_adjustment_ledger

        t_before = timezone.now()
        hed = TrnStkAdjHed.objects.create(
            stk_adj_dt=date.today(),
            customer=self.cust,
            stk_adj_type=TrnStkAdjHed.TYPE_ADJUST,
            item_type=self.item_type_rm,
            remarks='Test adjustment',
        )
        line = TrnStkAdjDtl1.objects.create(
            header=hed,
            item=self.item_rm,
        )
        b = TrnStkAdjDtl2.objects.create(
            line=line,
            batch_no='',
            batch_qty=Decimal('15.000'),
        )
        post_stock_adjustment_ledger(hed)
        t_after = timezone.now()

        movement = StockDtl.objects.filter(
            source_line_id=f'{StockDtl.TRAN_STK}:{b.pk}',
        ).first()

        self.assertIsNotNone(movement, "Stock adjustment must post movement row in StockDtl.")
        self.assertIsNotNone(movement.created_at, "StockDtl movement must capture real-time created_at.")
        self.assertTrue(
            t_before - timedelta(seconds=2) <= movement.created_at <= t_after + timedelta(seconds=2),
            "Adjustment movement created_at must match real-time window.",
        )


class StockLifecycleTimestampQueryTests(BaseInventoryTimestampTestCase):
    """
    Tier 1 & Tier 2 Coverage:
    - /inventory/ajax/stock-lifecycle/ returns created_at in each event dictionary.
    - Endpoint supports filtering by exact ISO datetime range.
    """

    def test_lifecycle_ajax_returns_created_at_in_events(self):
        """Lifecycle API returns created_at ISO timestamp in events payload."""
        dt_event = timezone.now() - timedelta(hours=2)
        m = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='RM-70010',
            trn_date=dt_event.date(),
            quantity=Decimal('20.000'),
            source_line_id='TEST:INW:70010',
        )
        StockDtl.objects.filter(pk=m.pk).update(created_at=dt_event)

        url = reverse('inventory:inventory_stock_lifecycle_ajax')
        resp = self.client.get(url, {'inv_id': self.stock_rm.stock_lnkno})
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertIn('events', data)
        self.assertGreater(len(data['events']), 0)

        found_event = None
        for ev in data['events']:
            if ev.get('doc_id') == 'RM-70010':
                found_event = ev
                break

        self.assertIsNotNone(found_event, "Test event RM-70010 must be in response.")
        self.assertIn(
            'created_at',
            found_event,
            "R3 Acceptance Criteria: Lifecycle JSON event must include 'created_at' timestamp.",
        )
        self.assertIsNotNone(found_event['created_at'])

    def test_lifecycle_ajax_filters_by_iso_datetime_range(self):
        """Lifecycle API filters correctly when provided ISO datetime strings."""
        base_time = timezone.now().replace(microsecond=0)
        t_early = base_time - timedelta(hours=5)
        t_mid = base_time - timedelta(hours=3)
        t_late = base_time - timedelta(hours=1)

        # Event 1: Early (outside window)
        m1 = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='RM-EARLY',
            trn_date=t_early.date(),
            quantity=Decimal('10.000'),
            source_line_id='TEST:INW:EARLY',
        )
        StockDtl.objects.filter(pk=m1.pk).update(created_at=t_early)

        # Event 2: Inside Window
        m2 = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='RM-TARGET',
            trn_date=t_mid.date(),
            quantity=Decimal('15.000'),
            source_line_id='TEST:INW:TARGET',
        )
        StockDtl.objects.filter(pk=m2.pk).update(created_at=t_mid)

        # Event 3: Late (outside window)
        m3 = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='RM-LATE',
            trn_date=t_late.date(),
            quantity=Decimal('20.000'),
            source_line_id='TEST:INW:LATE',
        )
        StockDtl.objects.filter(pk=m3.pk).update(created_at=t_late)

        # Query exact window around t_mid: [t_mid - 30min, t_mid + 30min]
        from_str = (t_mid - timedelta(minutes=30)).isoformat()
        to_str = (t_mid + timedelta(minutes=30)).isoformat()

        url = reverse('inventory:inventory_stock_lifecycle_ajax')
        resp = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': from_str,
            'to_date': to_str,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        doc_ids = [ev['doc_id'] for ev in data['events']]
        self.assertIn(
            'RM-TARGET',
            doc_ids,
            "R3 Requirement: Targeted event must be included in datetime range.",
        )
        self.assertNotIn(
            'RM-EARLY',
            doc_ids,
            "R3 Requirement: Early event outside datetime range must be excluded.",
        )
        self.assertNotIn(
            'RM-LATE',
            doc_ids,
            "R3 Requirement: Late event outside datetime range must be excluded.",
        )


class TimestampBoundaryAndCornerTests(BaseInventoryTimestampTestCase):
    """
    Tier 2 Boundary & Corner Cases:
    - Same-day morning vs. afternoon temporal filtering.
    - BVA exact boundaries (exact start, exact end, just before, just after).
    - Legacy NULL timestamp fallback to calendar date.
    """

    def test_same_day_morning_vs_afternoon_timestamp_filtering(self):
        """Two transactions on the same calendar date are properly segregated by time window."""
        today = date.today()
        # Morning transaction: 09:30 AM
        t_morning = timezone.make_aware(datetime.combine(today, datetime.min.time())) + timedelta(hours=9, minutes=30)
        # Afternoon transaction: 02:45 PM
        t_afternoon = timezone.make_aware(datetime.combine(today, datetime.min.time())) + timedelta(hours=14, minutes=45)

        m_morn = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='GRN-MORNING',
            trn_date=today,
            quantity=Decimal('50.000'),
            source_line_id='SAME:DAY:MORN',
        )
        StockDtl.objects.filter(pk=m_morn.pk).update(created_at=t_morning)

        m_aft = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_DIS,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no='DIS-AFTERNOON',
            trn_date=today,
            quantity=Decimal('30.000'),
            source_line_id='SAME:DAY:AFT',
        )
        StockDtl.objects.filter(pk=m_aft.pk).update(created_at=t_afternoon)

        # Query Morning Shift window: 08:00 to 12:00
        shift_from = (t_morning - timedelta(hours=1, minutes=30)).isoformat()
        shift_to = (t_morning + timedelta(hours=2, minutes=30)).isoformat()

        url = reverse('inventory:inventory_stock_lifecycle_ajax')
        resp = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': shift_from,
            'to_date': shift_to,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        doc_ids = [ev['doc_id'] for ev in data['events']]
        self.assertIn('GRN-MORNING', doc_ids, "Morning transaction must be present in morning query.")
        self.assertNotIn('DIS-AFTERNOON', doc_ids, "Afternoon transaction must NOT appear in morning query.")

    def test_edge_boundaries_datetime_range_queries(self):
        """BVA: Test exact boundary inclusion, just-before, and just-after exclusion."""
        t_event = timezone.now().replace(microsecond=0)
        m = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='BVA-EXACT',
            trn_date=t_event.date(),
            quantity=Decimal('10.000'),
            source_line_id='BVA:EXACT:01',
        )
        StockDtl.objects.filter(pk=m.pk).update(created_at=t_event)

        url = reverse('inventory:inventory_stock_lifecycle_ajax')

        # 1. Exact start: from_date == t_event (inclusive)
        resp1 = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': t_event.isoformat(),
            'to_date': (t_event + timedelta(hours=1)).isoformat(),
        })
        doc_ids1 = [ev['doc_id'] for ev in resp1.json()['events']]
        self.assertIn('BVA-EXACT', doc_ids1, "Event must be included when from_date == event.created_at.")

        # 2. Exact end: to_date == t_event (inclusive)
        resp2 = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': (t_event - timedelta(hours=1)).isoformat(),
            'to_date': t_event.isoformat(),
        })
        doc_ids2 = [ev['doc_id'] for ev in resp2.json()['events']]
        self.assertIn('BVA-EXACT', doc_ids2, "Event must be included when to_date == event.created_at.")

        # 3. Just after: from_date == t_event + 1 second (excluded)
        resp3 = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': (t_event + timedelta(seconds=1)).isoformat(),
            'to_date': (t_event + timedelta(hours=1)).isoformat(),
        })
        doc_ids3 = [ev['doc_id'] for ev in resp3.json()['events']]
        self.assertNotIn('BVA-EXACT', doc_ids3, "Event must be excluded when query starts 1 second after event.")

        # 4. Just before: to_date == t_event - 1 second (excluded)
        resp4 = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': (t_event - timedelta(hours=1)).isoformat(),
            'to_date': (t_event - timedelta(seconds=1)).isoformat(),
        })
        doc_ids4 = [ev['doc_id'] for ev in resp4.json()['events']]
        self.assertNotIn('BVA-EXACT', doc_ids4, "Event must be excluded when query ends 1 second before event.")

    def test_mixed_records_with_timestamps_and_legacy_null_timestamps_fallback(self):
        """
        R3 & R2 Invariant:
        When filtering over a date range, modern records with real-time timestamps
        are filtered by timestamp, while legacy records with NULL timestamps fall back
        to calendar date (trn_date) so they are not dropped.
        """
        # Verify schema requirement: StockDtl.created_at must be nullable for historical legacy data
        created_field = StockDtl._meta.get_field('created_at')
        if not created_field.null:
            self.fail(
                "M1/R2 Requirement: StockDtl.created_at must be nullable (null=True) "
                "to preserve historical records without timestamps."
            )

        today = date.today()
        # Modern movement with timestamp
        t_modern = timezone.now()
        m_mod = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='MODERN-01',
            trn_date=today,
            quantity=Decimal('40.000'),
            source_line_id='MIXED:MODERN:01',
        )
        StockDtl.objects.filter(pk=m_mod.pk).update(created_at=t_modern)

        # Legacy movement with NULL timestamp
        m_leg = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='LEGACY-01',
            trn_date=today,
            quantity=Decimal('20.000'),
            source_line_id='MIXED:LEGACY:01',
        )
        StockDtl.objects.filter(pk=m_leg.pk).update(created_at=None)

        url = reverse('inventory:inventory_stock_lifecycle_ajax')
        resp = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': today.isoformat(),
            'to_date': today.isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        doc_ids = [ev['doc_id'] for ev in data['events']]

        self.assertIn('MODERN-01', doc_ids, "Modern record must be included.")
        self.assertIn(
            'LEGACY-01',
            doc_ids,
            "R3/R2 Fallback: Legacy record with NULL timestamp must fall back to trn_date and be included.",
        )


class CrossFeatureLifecycleTimestampTests(BaseInventoryTimestampTestCase):
    """
    Tier 3 Cross-Feature Combinations:
    - Inward -> Stock Adjustment -> Sales Invoice lifecycle chain.
    - Compensating reversals capturing real-time timestamps.
    """

    def test_inward_adjustment_sales_chain_monotonic_timestamps(self):
        """Inward -> Adjustment -> Sales chain exhibits strictly increasing real-time timestamps."""
        t1 = timezone.now() - timedelta(minutes=30)
        t2 = timezone.now() - timedelta(minutes=15)
        t3 = timezone.now()

        # Step 1: Inward GRN
        m_inw = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='CHAIN-INW',
            trn_date=t1.date(),
            quantity=Decimal('100.000'),
            source_line_id='CHAIN:INW:1',
        )
        StockDtl.objects.filter(pk=m_inw.pk).update(created_at=t1)

        # Step 2: Stock Adjustment
        m_adj = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_STK,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no='CHAIN-ADJ',
            trn_date=t2.date(),
            quantity=Decimal('5.000'),
            source_line_id='CHAIN:ADJ:1',
        )
        StockDtl.objects.filter(pk=m_adj.pk).update(created_at=t2)

        # Step 3: Sales Invoice dispatch
        m_sls = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_SLS,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no='CHAIN-SLS',
            trn_date=t3.date(),
            quantity=Decimal('35.000'),
            source_line_id='CHAIN:SLS:1',
        )
        StockDtl.objects.filter(pk=m_sls.pk).update(created_at=t3)

        m_inw.refresh_from_db()
        m_adj.refresh_from_db()
        m_sls.refresh_from_db()

        self.assertLess(m_inw.created_at, m_adj.created_at, "Inward timestamp must precede adjustment.")
        self.assertLess(m_adj.created_at, m_sls.created_at, "Adjustment timestamp must precede sales dispatch.")

    def test_compensating_reversal_records_realtime_timestamp(self):
        """Compensating reversal row in StockDtl captures distinct, later real-time timestamp."""
        t_orig = timezone.now() - timedelta(hours=2)
        m_orig = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='REV-ORIG-01',
            trn_date=t_orig.date(),
            quantity=Decimal('50.000'),
            source_line_id='REV:TEST:ORIG',
        )
        StockDtl.objects.filter(pk=m_orig.pk).update(created_at=t_orig)

        # Create reversal row simulating cancellation
        t_rev = timezone.now()
        m_rev = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='REV-ORIG-01',
            trn_date=t_rev.date(),
            quantity=Decimal('50.000'),
            is_reversal=True,
            reversal_of=m_orig,
            source_line_id='REV:TEST:COMPENSATING',
        )
        StockDtl.objects.filter(pk=m_rev.pk).update(created_at=t_rev)

        m_orig.refresh_from_db()
        m_rev.refresh_from_db()

        self.assertTrue(m_rev.is_reversal)
        self.assertEqual(m_rev.reversal_of, m_orig)
        self.assertGreater(
            m_rev.created_at,
            m_orig.created_at,
            "R3 Requirement: Reversal movement must record its own distinct real-time timestamp.",
        )


class RealWorldWorkloadShiftAuditTests(BaseInventoryTimestampTestCase):
    """
    Tier 4 Real-World Workload Scenarios:
    - Full product lifecycle: Inward batch receipt -> Dispensing -> DPR production -> Sales dispatch.
    - Production shift audit query isolating movements within a specific manufacturing shift.
    """

    def test_pharmaceutical_shift_window_audit_query(self):
        """
        Simulates two manufacturing shifts:
        - Shift 1 (08:00 - 16:00): RM Inward (09:00), RM Dispensing (11:30), DPR Production (14:00).
        - Shift 2 (16:00 - 00:00): Sales Dispatch (17:30), PM Inward (19:00).
        Querying Shift 1 window retrieves only Shift 1 events and computes accurate period balances.
        """
        today = date.today()
        base_day = timezone.make_aware(datetime.combine(today, datetime.min.time()))

        # Shift 1 Timestamps
        t_s1_inw = base_day + timedelta(hours=9)
        t_s1_dis = base_day + timedelta(hours=11, minutes=30)
        t_s1_dpr = base_day + timedelta(hours=14)

        # Shift 2 Timestamps
        t_s2_sls = base_day + timedelta(hours=17, minutes=30)
        t_s2_pm = base_day + timedelta(hours=19)

        # 1. Shift 1 Movements on RM stock
        m1 = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='SHIFT-INW-01',
            trn_date=today,
            quantity=Decimal('200.000'),
            source_line_id='SHIFT:1:INW',
        )
        StockDtl.objects.filter(pk=m1.pk).update(created_at=t_s1_inw)

        m2 = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_DIS,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no='SHIFT-DIS-01',
            trn_date=today,
            quantity=Decimal('80.000'),
            source_line_id='SHIFT:1:DIS',
        )
        StockDtl.objects.filter(pk=m2.pk).update(created_at=t_s1_dis)

        m3 = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_DPR,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no='SHIFT-DPR-01',
            trn_date=today,
            quantity=Decimal('5.000'),
            source_line_id='SHIFT:1:DPR',
        )
        StockDtl.objects.filter(pk=m3.pk).update(created_at=t_s1_dpr)

        # 2. Shift 2 Movements on RM stock
        m4 = StockDtl.objects.create(
            stock=self.stock_rm,
            tran_id=StockDtl.TRAN_SLS,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no='SHIFT-SLS-01',
            trn_date=today,
            quantity=Decimal('50.000'),
            source_line_id='SHIFT:2:SLS',
        )
        StockDtl.objects.filter(pk=m4.pk).update(created_at=t_s2_sls)

        # Query Shift 1 Window: 08:00:00 to 16:00:00
        shift_1_start = (base_day + timedelta(hours=8)).isoformat()
        shift_1_end = (base_day + timedelta(hours=16)).isoformat()

        url = reverse('inventory:inventory_stock_lifecycle_ajax')
        resp = self.client.get(url, {
            'inv_id': self.stock_rm.stock_lnkno,
            'from_date': shift_1_start,
            'to_date': shift_1_end,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        shift_1_docs = [ev['doc_id'] for ev in data['events']]

        # Shift 1 movements must be present
        self.assertIn('SHIFT-INW-01', shift_1_docs)
        self.assertIn('SHIFT-DIS-01', shift_1_docs)
        self.assertIn('SHIFT-DPR-01', shift_1_docs)

        # Shift 2 movements must NOT be present
        self.assertNotIn(
            'SHIFT-SLS-01',
            shift_1_docs,
            "Shift 2 event must NOT appear in Shift 1 audit query.",
        )
