from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from masters.models import FinancialYear, MstCust, MstProdCat, MstState, MstSupplier, MstTransport
from transactions.models import TrnInwHed
from transactions.numbering import max_grn_sequence_for_fy, suggested_grn_no
from transactions.utils import (
    get_financial_year_from_date,
    get_working_year_for_date,
    rollover_financial_year,
    validate_fy_closure,
    validate_transaction_in_open_fy,
)


class WorkingYearForDateTests(TestCase):
    def test_mar_31_uses_prior_start_year(self):
        self.assertEqual(get_working_year_for_date(date(2026, 3, 31)), (2025, 2026))

    def test_apr_1_uses_current_start_year(self):
        self.assertEqual(get_working_year_for_date(date(2026, 4, 1)), (2026, 2027))

    def test_leap_feb_in_fy(self):
        self.assertEqual(get_working_year_for_date(date(2024, 2, 29)), (2023, 2024))


class FinancialYearLookupAndFormRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )

    def test_get_financial_year_from_date(self):
        fy = get_financial_year_from_date(date(2026, 1, 15))
        self.assertEqual(fy.fy_display, '2025-26')

    def test_validate_transaction_creates_fy_if_missing(self):
        self.assertFalse(FinancialYear.objects.filter(fy_start_year=2010).exists())
        fy = validate_transaction_in_open_fy(date(2010, 6, 1))
        self.assertTrue(FinancialYear.objects.filter(fy_start_year=2010).exists())
        self.assertEqual(fy.fy_start_year, 2010)
        self.assertTrue(fy.is_open)

    def test_validate_transaction_closed_fy(self):
        # Cannot mark the current FY closed at DB level; clear current first.
        FinancialYear.objects.filter(fy_start_year=2025).update(is_current=False)
        FinancialYear.objects.filter(fy_start_year=2025).update(is_open=False, is_closed=True)
        with self.assertRaises(ValidationError):
            validate_transaction_in_open_fy(date(2026, 1, 15))


class RolloverAndClosureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        FinancialYear.objects.create(
            fy_start_year=2024,
            fy_end_year=2025,
            fy_display='2024-25',
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )
        FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=False,
            is_open=True,
            is_closed=False,
        )

    def test_rollover_marks_new_current_and_opens(self):
        rollover_financial_year(2025)
        old = FinancialYear.objects.get(fy_start_year=2024)
        new = FinancialYear.objects.get(fy_start_year=2025)
        self.assertFalse(old.is_current)
        self.assertTrue(new.is_current)
        self.assertTrue(new.is_open)
        self.assertFalse(new.is_closed)

    def test_validate_fy_closure_blocks_current_before_end(self):
        FinancialYear.objects.all().delete()
        fy = FinancialYear.objects.create(
            fy_start_year=2030,
            fy_end_year=2031,
            fy_display='2030-31',
            start_date=date(2030, 4, 1),
            end_date=date(2031, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )
        with self.assertRaises(ValidationError):
            validate_fy_closure(fy)


class TrnInwHedFinancialYearAssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        st = MstState.objects.create(state_name='Test State FY', gst_code='99')
        cls.cat = MstProdCat.objects.create(prod_cat_id='RM', prod_cat_name='Raw Material')
        cls.customer = MstCust.objects.create(
            cust_name='Cust FY',
            short_name='CFY',
            address='Addr',
            state=st,
        )
        cls.supplier = MstSupplier.objects.create(
            supl_name='Supl FY',
            short_name='SFY',
            address='Addr',
            state=st,
            pin_code='400001',
        )
        cls.transport = MstTransport.objects.create(transport_name='Trans FY')
        FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )

    def test_save_sets_financial_year_and_working_year(self):
        hed = TrnInwHed(
            inward_dt=date(2026, 1, 10),
            customer=self.customer,
            register_no='R-99001',
            grn_category=self.cat,
            grn_no='RM-99001',
            supplier=self.supplier,
            inv_no='INV-1',
            inv_dt=date(2026, 1, 5),
            transporter=self.transport,
            vehicle_no='MH01AB1234',
        )
        hed.save()
        hed.refresh_from_db()
        self.assertEqual(hed.working_year, '2025-26')
        self.assertEqual(hed.financial_year.fy_start_year, 2025)


class GrnNumberingPerFinancialYearTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        st = MstState.objects.create(state_name='Test State GRN', gst_code='98')
        cls.cat = MstProdCat.objects.create(prod_cat_id='RM', prod_cat_name='Raw Material')
        cls.customer = MstCust.objects.create(
            cust_name='Cust GRN',
            short_name='CGRN',
            address='Addr',
            state=st,
        )
        cls.supplier = MstSupplier.objects.create(
            supl_name='Supl GRN',
            short_name='SGRN',
            address='Addr',
            state=st,
            pin_code='400001',
        )
        cls.transport = MstTransport.objects.create(transport_name='Trans GRN')
        FinancialYear.objects.create(
            fy_start_year=2024,
            fy_end_year=2025,
            fy_display='2024-25',
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_current=False,
            is_open=True,
            is_closed=False,
        )
        FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=False,
            is_open=True,
            is_closed=False,
        )

    def _mk(self, inward_dt, grn_no):
        # Register no. is globally unique (not FY-scoped), so keep it unique across rows.
        reg_n = 99000 + TrnInwHed.objects.count() + 1
        return TrnInwHed.objects.create(
            inward_dt=inward_dt,
            customer=self.customer,
            register_no=f'R-{reg_n}',
            grn_category=self.cat,
            grn_no=grn_no,
            supplier=self.supplier,
            inv_no='INV-1',
            inv_dt=inward_dt,
            transporter=self.transport,
            vehicle_no='MH01AB1234',
        )

    def test_grn_can_repeat_across_fys(self):
        self._mk(date(2025, 3, 31), 'RM-00001')  # FY 2024-25
        self._mk(date(2025, 4, 1), 'RM-00001')   # FY 2025-26
        self.assertEqual(TrnInwHed.objects.filter(grn_no='RM-00001').count(), 2)

    def test_grn_unique_within_same_fy(self):
        self._mk(date(2025, 4, 1), 'RM-00001')
        with self.assertRaises(Exception):
            self._mk(date(2025, 4, 2), 'RM-00001')

    def test_sequential_generation_per_fy(self):
        self._mk(date(2025, 3, 31), 'RM-00001')  # FY 2024-25
        self._mk(date(2025, 3, 31), 'RM-00002')
        self.assertEqual(max_grn_sequence_for_fy('2024-25'), 2)
        self.assertEqual(suggested_grn_no('RM', '2024-25'), 'RM-00003')

        # FY 2025-26 empty → reset to 00001
        self.assertEqual(max_grn_sequence_for_fy('2025-26'), 0)
        self.assertEqual(suggested_grn_no('RM', '2025-26'), 'RM-00001')


class FinancialYearModelConstraintTests(TestCase):
    def test_only_one_current(self):
        FinancialYear.objects.create(
            fy_start_year=2024,
            fy_end_year=2025,
            fy_display='2024-25',
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )
        dup = FinancialYear(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )
        with self.assertRaises(ValidationError):
            dup.save()

from django.test import TestCase

# Create your tests here.
