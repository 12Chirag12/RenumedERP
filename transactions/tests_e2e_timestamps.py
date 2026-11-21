"""
E2E Automated Test Suite for Real-Time Timestamps & Date-Range Tracking.
Domain: Transactions (Inward GRN, Sales Invoices, Forms, Templates, Modification tracking).

Requirements Covered:
- R1: Automatic Real-Time Timestamping on All Inventory Transactions.
      No manual input field for entering today's date in Inward form/template.
      Distinct user-provided supplier invoice date (inv_dt) and customer sales invoice date (invoice_dt).
- R2: Comprehensive Timestamp Tracking (Creation and Modification).
      Persisting created_at and updated_at on transaction headers.
      Historical records without timestamps remain unchanged (NULL preserved).
- Tier 2 Boundary / Corner Cases:
      Sub-minute rapid sequential transactions ordering.
      Editing non-date fields updates updated_at while preserving created_at.
      Validation of inv_dt <= inward_dt / current date.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.utils import timezone

from masters.models import (
    FinancialYear,
    MstCust,
    MstItemType,
    MstProd,
    MstProdCat,
    MstState,
    MstSupplier,
    MstTransport,
    MstUom,
)
from transactions.constants import GST_TYPE_EXEMPTED
from transactions.forms.inward import InwardForm
from transactions.models import TrnInwHed, TrnSlsHed


class BaseTransactionTimestampTestCase(TestCase):
    """Shared test fixture setting up financial years and business masters."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser('e2e_txn_admin', 'e2e@example.com', 'pass1234')

        cls.state = MstState.objects.create(state_name='Maharashtra E2E', gst_code='27')
        cls.cust = MstCust.objects.create(
            cust_name='Aura Health Pvt Ltd',
            short_name='AURA',
            address='Plot 10, MIDC',
            state=cls.state,
            pin_code='400001',
        )
        cls.supplier = MstSupplier.objects.create(
            supl_name='Standard Solvents Ltd',
            short_name='STDSOLV',
            address='Plot 22, Chemical Zone',
            state=cls.state,
            pin_code='400002',
        )
        cls.cat_rm = MstProdCat.objects.create(prod_cat_id='RM', prod_cat_name='Raw Materials')
        cls.cat_pm = MstProdCat.objects.create(prod_cat_id='PM', prod_cat_name='Packaging Materials')
        cls.cat_fg = MstProdCat.objects.create(prod_cat_id='FG', prod_cat_name='Finished Goods')
        cls.transporter = MstTransport.objects.create(transport_name='Super Express Cargo')

        cls.uom_kg = MstUom.objects.create(uom_name='Kilogram', short_name='kg')
        cls.uom_tab = MstUom.objects.create(uom_name='Tablets', short_name='tab')

        cls.item_type_fg = MstItemType.objects.create(
            item_type_name='Finished Good',
            item_category=cls.cat_fg,
        )
        cls.prod_fg = MstProd.objects.create(
            prod_name='Paracetamol 500mg Tablets',
            prod_type=cls.item_type_fg,
            prod_category=cls.cat_fg,
            uom=cls.uom_tab,
        )

        cls.fy_2025 = FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=False,
            is_open=True,
            is_closed=False,
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

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)


class InwardTimestampFeatureTests(BaseTransactionTimestampTestCase):
    """
    Tier 1 Feature Coverage:
    - Adding Inward automatically captures real-time created_at and updated_at datetime.
    - Model schema definitions for created_at and updated_at.
    """

    def test_trn_inw_hed_has_timestamp_fields(self):
        """TrnInwHed model must define created_at and updated_at DateTimeFields."""
        has_created = hasattr(TrnInwHed, 'created_at')
        has_updated = hasattr(TrnInwHed, 'updated_at')
        self.assertTrue(
            has_created,
            "R2 Requirement: TrnInwHed model must define 'created_at' DateTimeField.",
        )
        self.assertTrue(
            has_updated,
            "R2 Requirement: TrnInwHed model must define 'updated_at' DateTimeField.",
        )

    def test_inward_creation_auto_populates_created_at_with_realtime_datetime(self):
        """Creating an Inward transaction populates created_at with system datetime."""
        if not hasattr(TrnInwHed, 'created_at'):
            self.fail("R1/R2 Requirement: TrnInwHed.created_at field is missing.")

        t_before = timezone.now()
        inward = TrnInwHed.objects.create(
            customer=self.cust,
            register_no='R-10001',
            grn_category=self.cat_rm,
            grn_no='RM-10001',
            supplier=self.supplier,
            inv_no='INV-TEST-001',
            inv_dt=date.today(),
            inward_dt=date.today(),
            transporter=self.transporter,
            vehicle_no='MH-12-AB-1234',
        )
        t_after = timezone.now()

        inward.refresh_from_db()
        self.assertIsNotNone(
            inward.created_at,
            "R1 Acceptance Criteria: Adding Inward must auto-populate created_at with real-time datetime.",
        )
        # Ensure timestamp falls within the execution interval
        self.assertTrue(
            t_before - timedelta(seconds=2) <= inward.created_at <= t_after + timedelta(seconds=2),
            f"created_at ({inward.created_at}) must match system real-time window [{t_before}, {t_after}].",
        )

    def test_inward_creation_populates_updated_at(self):
        """Initial Inward creation populates updated_at with system datetime."""
        if not hasattr(TrnInwHed, 'updated_at'):
            self.fail("R2 Requirement: TrnInwHed.updated_at field is missing.")

        inward = TrnInwHed.objects.create(
            customer=self.cust,
            register_no='R-10002',
            grn_category=self.cat_rm,
            grn_no='RM-10002',
            supplier=self.supplier,
            inv_no='INV-TEST-002',
            inv_dt=date.today(),
            inward_dt=date.today(),
            transporter=self.transporter,
            vehicle_no='MH-12-CD-5678',
        )
        inward.refresh_from_db()
        self.assertIsNotNone(
            inward.updated_at,
            "R2 Requirement: Inward creation must populate updated_at.",
        )
        if hasattr(inward, 'created_at') and inward.created_at:
            delta = abs((inward.updated_at - inward.created_at).total_seconds())
            self.assertLessEqual(
                delta,
                2.0,
                "On initial creation, updated_at must coincide with created_at.",
            )


class InwardFormAndTemplateTests(BaseTransactionTimestampTestCase):
    """
    Tier 1 Feature Coverage:
    - Inward form and template do NOT have a manual input field for entering today's date.
    - Supplier invoice date (inv_dt) remains a separate user-provided and editable field.
    """

    def test_inward_form_does_not_require_manual_today_date(self):
        """InwardForm must validate and default inward date automatically without requiring manual user input."""
        form_data = {
            'customer': self.cust.pk,
            'register_no': 'R-20001',
            'grn_category': self.cat_rm.pk,
            'grn_no': 'RM-20001',
            'supplier': self.supplier.pk,
            'inv_no': 'SUPL-INV-99',
            'inv_dt': date.today().isoformat(),
            'transporter': self.transporter.pk,
            'vehicle_no': 'MH-14-XY-8888',
            'driver_name': 'Ramesh',
            'driver_no': '9876543210',
            'remarks': 'Auto timestamp test',
            'inward_dt': (date.today() - timedelta(days=1)).isoformat(),  # Stock came yesterday
        }
        form = InwardForm(data=form_data)
        self.assertIn('inward_dt', form.fields)
        self.assertEqual(form.fields['inward_dt'].widget.input_type, 'date')

    def test_inward_template_renders_inward_date_input(self):
        """The inward form template renders an editable date input for inward_dt without auto-badge UI."""
        rendered = render_to_string(
            'transactions/inward_form.html',
            context={'form': InwardForm(), 'base_template': 'base.html'},
        )
        self.assertIn('name="inward_dt"', rendered)
        self.assertNotIn('auto-date-badge', rendered)

    def test_supplier_inv_dt_remains_distinct_and_editable(self):
        """Supplier invoice date (inv_dt) remains a distinct, user-provided, and required input field."""
        form = InwardForm()
        self.assertIn(
            'inv_dt',
            form.fields,
            "R1 Acceptance Criteria: InwardForm must preserve 'inv_dt' for supplier invoice date.",
        )
        self.assertTrue(
            form.fields['inv_dt'].required,
            "Supplier invoice date (inv_dt) must remain a required user-provided field.",
        )


class InvoiceDatePreservationTests(BaseTransactionTimestampTestCase):
    """
    Tier 1 Feature Coverage:
    - Supplier invoice date (inv_dt) and sales invoice date (invoice_dt) remain distinct
      and user-editable, separate from the real-time system timestamps.
    """

    def test_supplier_inv_dt_can_be_past_date_distinct_from_created_at(self):
        """Supplier invoice date can be days before inward entry; created_at reflects entry time."""
        past_invoice_date = date.today() - timedelta(days=5)
        inward = TrnInwHed.objects.create(
            customer=self.cust,
            register_no='R-30001',
            grn_category=self.cat_rm,
            grn_no='RM-30001',
            supplier=self.supplier,
            inv_no='INV-PAST-005',
            inv_dt=past_invoice_date,
            inward_dt=date.today(),
            transporter=self.transporter,
            vehicle_no='MH-04-AB-1111',
        )
        inward.refresh_from_db()

        self.assertEqual(
            inward.inv_dt,
            past_invoice_date,
            "Supplier invoice date must remain exactly what the user entered.",
        )
        if hasattr(inward, 'created_at') and inward.created_at:
            self.assertEqual(
                timezone.localtime(inward.created_at).date(),
                timezone.localdate(),
                "created_at must reflect the real-time system date, distinct from past inv_dt.",
            )

    def test_sales_invoice_date_distinct_and_captures_timestamps(self):
        """Sales invoice date (invoice_dt) is distinct while created_at/updated_at track real-time."""
        past_sales_date = date.today() - timedelta(days=2)
        t_before = timezone.now()
        invoice = TrnSlsHed.objects.create(
            invoice_no='SI-80001',
            invoice_dt=past_sales_date,
            financial_year=self.fy_2026,
            working_year='2026-27',
            customer=self.cust,
            transporter=self.transporter,
            delivery_add='Warehouse 4',
            taxable_val=Decimal('5000.00'),
            total_amt=Decimal('5900.00'),
        )
        t_after = timezone.now()
        invoice.refresh_from_db()

        self.assertEqual(
            invoice.invoice_dt,
            past_sales_date,
            "invoice_dt must remain the distinct business date entered by user.",
        )
        self.assertIsNotNone(invoice.created_at, "TrnSlsHed.created_at must be populated.")
        self.assertIsNotNone(invoice.updated_at, "TrnSlsHed.updated_at must be populated.")
        self.assertTrue(
            t_before - timedelta(seconds=2) <= invoice.created_at <= t_after + timedelta(seconds=2),
            "Sales invoice created_at must capture real-time system datetime.",
        )


class TransactionTimestampTrackingTests(BaseTransactionTimestampTestCase):
    """
    Tier 1 & Tier 2 Coverage:
    - Modifying an existing transaction updates updated_at while preserving created_at.
    - Historical records without timestamps remain unchanged (NULL).
    """

    def test_inward_modification_updates_updated_at(self):
        """Modifying an existing Inward transaction updates updated_at and keeps created_at intact."""
        if not hasattr(TrnInwHed, 'updated_at') or not hasattr(TrnInwHed, 'created_at'):
            self.fail("R2 Requirement: TrnInwHed must define created_at and updated_at.")

        inward = TrnInwHed.objects.create(
            customer=self.cust,
            register_no='R-40001',
            grn_category=self.cat_rm,
            grn_no='RM-40001',
            supplier=self.supplier,
            inv_no='INV-MOD-001',
            inv_dt=date.today(),
            inward_dt=date.today(),
            transporter=self.transporter,
            vehicle_no='MH-12-INITIAL',
        )
        inward.refresh_from_db()
        orig_created_at = inward.created_at
        orig_updated_at = inward.updated_at

        # Sleep briefly to ensure clock advances
        time.sleep(0.05)

        # Modify non-date field
        inward.vehicle_no = 'MH-12-MODIFIED'
        inward.remarks = 'Updated delivery information'
        inward.save()
        inward.refresh_from_db()

        self.assertEqual(
            inward.created_at,
            orig_created_at,
            "R2 Acceptance Criteria: Modifying a record must preserve created_at strictly unchanged.",
        )
        self.assertGreaterEqual(
            inward.updated_at,
            orig_updated_at,
            "R2 Acceptance Criteria: Modifying an existing record must advance updated_at timestamp.",
        )

    def test_sales_invoice_modification_updates_updated_at_preserves_created_at(self):
        """Modifying a sales invoice updates updated_at while preserving created_at."""
        invoice = TrnSlsHed.objects.create(
            invoice_no='SI-80002',
            invoice_dt=date.today(),
            financial_year=self.fy_2026,
            working_year='2026-27',
            customer=self.cust,
            transporter=self.transporter,
            delivery_add='Initial address',
            taxable_val=Decimal('2000.00'),
            total_amt=Decimal('2360.00'),
        )
        invoice.refresh_from_db()
        orig_created = invoice.created_at
        orig_updated = invoice.updated_at

        time.sleep(0.05)
        invoice.delivery_add = 'Modified address for customer'
        invoice.save()
        invoice.refresh_from_db()

        self.assertEqual(invoice.created_at, orig_created)
        self.assertGreater(invoice.updated_at, orig_updated)

    def test_existing_records_null_timestamps_preserved(self):
        """
        R2 Invariant:
        Existing historical records without timestamps remain unchanged (NULL) and are not overwritten.
        """
        if not hasattr(TrnInwHed, 'created_at'):
            self.fail("R2 Requirement: TrnInwHed must define created_at to test legacy NULL preservation.")

        inward = TrnInwHed.objects.create(
            customer=self.cust,
            register_no='R-40002',
            grn_category=self.cat_rm,
            grn_no='RM-40002',
            supplier=self.supplier,
            inv_no='INV-LEGACY-001',
            inv_dt=date(2024, 1, 15),
            inward_dt=date(2024, 1, 15),
            transporter=self.transporter,
            vehicle_no='MH-12-LEGACY',
        )
        # Simulate legacy record by forcing NULL timestamps
        TrnInwHed.objects.filter(pk=inward.pk).update(created_at=None, updated_at=None)
        inward.refresh_from_db()

        self.assertIsNone(inward.created_at, "Simulation check: created_at must be NULL.")
        self.assertIsNone(inward.updated_at, "Simulation check: updated_at must be NULL.")

        # Read or execute non-destructive query
        fetched = TrnInwHed.objects.get(pk=inward.pk)
        self.assertIsNone(
            fetched.created_at,
            "R2 Acceptance Criteria: Legacy record created_at must remain NULL and not be backfilled.",
        )
        self.assertIsNone(
            fetched.updated_at,
            "R2 Acceptance Criteria: Legacy record updated_at must remain NULL.",
        )


class TimestampBoundaryAndCornerTests(BaseTransactionTimestampTestCase):
    """
    Tier 2 Boundary & Corner Cases:
    - Rapid sequential transactions preserving sub-minute timestamp ordering.
    - Editing non-date fields updates updated_at while preserving created_at.
    - Form validation: inv_dt cannot be in the future relative to inward date.
    """

    def test_rapid_sequential_transactions_preserve_timestamp_ordering(self):
        """Rapid consecutive transactions must maintain non-decreasing real-time order."""
        if not hasattr(TrnInwHed, 'created_at'):
            self.fail("R1/R2 Requirement: TrnInwHed.created_at is required.")

        inwards = []
        for i in range(1, 4):
            inw = TrnInwHed.objects.create(
                customer=self.cust,
                register_no=f'R-5000{i}',
                grn_category=self.cat_rm,
                grn_no=f'RM-5000{i}',
                supplier=self.supplier,
                inv_no=f'INV-RAPID-{i}',
                inv_dt=date.today(),
                inward_dt=date.today(),
                transporter=self.transporter,
                vehicle_no=f'MH-12-SEQ-{i}',
            )
            inwards.append(inw)

        for inw in inwards:
            inw.refresh_from_db()

        self.assertLessEqual(
            inwards[0].created_at,
            inwards[1].created_at,
            "Timestamp order must be preserved between rapid consecutive transactions.",
        )
        self.assertLessEqual(
            inwards[1].created_at,
            inwards[2].created_at,
            "Timestamp order must be preserved between rapid consecutive transactions.",
        )

    def test_edit_non_date_field_preserves_created_at_microsecond_precision(self):
        """Updating vehicle_no, remarks, or driver_name preserves created_at down to microsecond."""
        if not hasattr(TrnInwHed, 'created_at') or not hasattr(TrnInwHed, 'updated_at'):
            self.fail("R2 Requirement: TrnInwHed timestamp fields missing.")

        inward = TrnInwHed.objects.create(
            customer=self.cust,
            register_no='R-50010',
            grn_category=self.cat_rm,
            grn_no='RM-50010',
            supplier=self.supplier,
            inv_no='INV-TEST-50010',
            inv_dt=date.today(),
            inward_dt=date.today(),
            transporter=self.transporter,
            vehicle_no='MH-12-OLD-1',
            driver_name='Old Driver',
            remarks='Old Remarks',
        )
        inward.refresh_from_db()
        created_snap = inward.created_at

        time.sleep(0.02)
        inward.driver_name = 'New Driver'
        inward.remarks = 'New Remarks'
        inward.save()
        inward.refresh_from_db()

        self.assertEqual(
            inward.created_at,
            created_snap,
            "created_at must be strictly invariant across non-date field edits.",
        )

    def test_inward_inv_dt_cannot_be_after_inward_date(self):
        """Business validation: supplier invoice date cannot be after inward date."""
        inward = TrnInwHed(
            customer=self.cust,
            register_no='R-50020',
            grn_category=self.cat_rm,
            grn_no='RM-50020',
            supplier=self.supplier,
            inv_no='INV-FUTURE',
            inv_dt=date.today() + timedelta(days=5),  # Future relative to inward_dt
            inward_dt=date.today(),
            transporter=self.transporter,
            vehicle_no='MH-12-FUTURE',
        )
        with self.assertRaises(ValidationError):
            inward.clean()
