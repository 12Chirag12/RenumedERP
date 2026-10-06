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
    def test_inward_transporter_optional(self):
        reg_n = 99000 + TrnInwHed.objects.count() + 1
        hed = TrnInwHed.objects.create(
            inward_dt=date(2025, 4, 1),
            customer=self.customer,
            register_no=f'R-{reg_n}',
            grn_category=self.cat,
            grn_no=f'RM-{reg_n}',
            supplier=self.supplier,
            inv_no='INV-OPTIONAL-TRANS',
            inv_dt=date(2025, 4, 1),
            transporter=None,
            vehicle_no='',
        )
        self.assertIsNone(hed.transporter)
        self.assertIsNone(hed.transporter_id)



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

class InwardProductsDisplayTests(TestCase):
    def test_products_display_property(self):
        hed = TrnInwHed()
        self.assertEqual(hed.products_display, '')


class LogSheetViewAndAjaxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from masters.models import (
            MstCustProd,
            MstDepartment,
            MstItemType,
            MstPkgStyle,
            MstProd,
            MstSection,
            MstUom,
        )
        from transactions.constants import GST_TYPE_EXEMPTED
        from transactions.models import (
            LOGSHEET_LAYER_SLOT_SINGLE,
            LOGSHEET_SHIFT_DAY,
            LOGSHEET_SHIFT_NIGHT,
            TrnBatchDtl,
            TrnBatchHed,
            TrnLogSheet,
            TrnSlsOrdDtl1,
            TrnSlsOrdHed,
        )
        from decimal import Decimal

        cls.user = get_user_model().objects.create_superuser('lsadmin', 'ls@example.com', 'adminpass')
        cls.fy = FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )
        cls.state = MstState.objects.create(state_name='Maharashtra', gst_code='27')
        cls.cat = MstProdCat.objects.create(prod_cat_id='TB', prod_cat_name='Tablet')
        cls.item_type = MstItemType.objects.create(item_type_name='Finished Good', item_category=cls.cat)
        cls.uom = MstUom.objects.create(uom_name='Tablet', short_name='TAB')
        cls.pkg_style = MstPkgStyle.objects.create(
            pkg_style_name='10x10 Blister',
            pkg_style_value=100,
            pkg_type=cls.item_type,
        )
        cls.dept = MstDepartment.objects.create(dept_name='Production')
        cls.section = MstSection.objects.create(section_name='Granulation-I', department=cls.dept)
        cls.customer = MstCust.objects.create(
            cust_name='Aura Laboratories Pvt Ltd',
            short_name='AURA',
            address='123 Test Park',
            state=cls.state,
            pin_code='400001',
        )
        cls.product = MstProd.objects.create(
            prod_name='Paracetamol 500mg',
            generic_name='Paracetamol',
            prod_type=cls.item_type,
            prod_category=cls.cat,
            uom=cls.uom,
            tablet_layer=MstProd.LAYER_SINGLE,
        )
        MstCustProd.objects.create(
            customer=cls.customer,
            product=cls.product,
            adv_license='N',
            batch_abbr='AUR',
        )
        cls.order = TrnSlsOrdHed.objects.create(
            ord_rec_dt=date(2025, 5, 10),
            customer=cls.customer,
            cust_ord_id='ORD-001',
            cust_ord_date=date(2025, 5, 10),
        )
        cls.order_line = TrnSlsOrdDtl1.objects.create(
            order=cls.order,
            product=cls.product,
            hsn_no='300490',
            packing_style=cls.pkg_style,
            order_qty=Decimal('100.00'),
            remaining_qty=Decimal('100.00'),
            ord_qty_nos=Decimal('100000'),
            rate=Decimal('1.50'),
            taxable_amt=Decimal('150.00'),
            gst_type=GST_TYPE_EXEMPTED,
            gst_per=Decimal('0.00'),
            prod_amt=Decimal('150.00'),
            export_type='DOMESTIC',
        )
        cls.batch_hed = TrnBatchHed.objects.create(
            customer=cls.customer,
            order=cls.order,
            order_line=cls.order_line,
            product=cls.product,
            batch_size_l=Decimal('1.00000'),
            batch_size_n=Decimal('100000'),
            batch_abbr='AUR',
            batch_from=1,
            batch_to=1,
        )
        cls.batch_line = TrnBatchDtl.objects.create(
            batch=cls.batch_hed,
            batch_no='AUR001',
            batch_qty_l=Decimal('1.00000'),
            batch_qty_n=Decimal('100000'),
            mfg_dt='MAY-2025',
            exp_dt='APR-2028',
            log_sheet_flg='N',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_logsheet_list_ajax_returns_customer_short_name_and_delete_url(self):
        from transactions.models import (
            LOGSHEET_LAYER_SLOT_SINGLE,
            LOGSHEET_SHIFT_DAY,
            TrnLogSheet,
        )
        logsheet = TrnLogSheet.objects.create(
            section=self.section,
            gran_dt=date(2025, 5, 12),
            customer=self.customer,
            shift_id=LOGSHEET_SHIFT_DAY,
            product=self.product,
            batch_line=self.batch_line,
            layer_slot=LOGSHEET_LAYER_SLOT_SINGLE,
            dpr_flg='N',
            rm_disp_flg='N',
        )
        self.batch_line.log_sheet_flg = 'Y'
        self.batch_line.save(update_fields=['log_sheet_flg'])

        from django.urls import reverse
        url = reverse('transactions:logsheet_list_ajax')
        resp = self.client.get(url, {'start': '2025-05-01', 'end': '2025-05-31'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('rows', data)
        self.assertEqual(len(data['rows']), 1)
        row = data['rows'][0]
        # Verify customer short name is returned
        self.assertEqual(row['customer'], 'AURA')
        # Verify delete_url is returned
        expected_delete_url = reverse('transactions:log_sheet_delete', args=[logsheet.pk])
        self.assertEqual(row['delete_url'], expected_delete_url)

    def test_logsheet_view_get_with_edit_pk(self):
        from transactions.models import (
            LOGSHEET_LAYER_SLOT_SINGLE,
            LOGSHEET_SHIFT_DAY,
            TrnLogSheet,
        )
        logsheet = TrnLogSheet.objects.create(
            section=self.section,
            gran_dt=date(2025, 5, 12),
            customer=self.customer,
            shift_id=LOGSHEET_SHIFT_DAY,
            product=self.product,
            batch_line=self.batch_line,
            layer_slot=LOGSHEET_LAYER_SLOT_SINGLE,
            dpr_flg='N',
            rm_disp_flg='N',
        )
        from django.urls import reverse
        url = reverse('transactions:log_sheet')
        resp = self.client.get(url, {'edit_pk': logsheet.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('edit_instance', resp.context)
        self.assertEqual(resp.context['edit_instance'].pk, logsheet.pk)
        payload = resp.context['edit_payload']
        self.assertIsNotNone(payload)
        self.assertEqual(payload['customer_id'], self.customer.pk)
        self.assertEqual(payload['product_id'], self.product.pk)
        self.assertEqual(payload['batch_dtl_id'], self.batch_line.pk)
        self.assertEqual(payload['batch_no'], 'AUR001')

    def test_logsheet_view_post_edit_updates_record(self):
        from transactions.models import (
            LOGSHEET_LAYER_SLOT_SINGLE,
            LOGSHEET_SHIFT_DAY,
            LOGSHEET_SHIFT_NIGHT,
            TrnLogSheet,
        )
        logsheet = TrnLogSheet.objects.create(
            section=self.section,
            gran_dt=date(2025, 5, 12),
            customer=self.customer,
            shift_id=LOGSHEET_SHIFT_DAY,
            product=self.product,
            batch_line=self.batch_line,
            layer_slot=LOGSHEET_LAYER_SLOT_SINGLE,
            dpr_flg='N',
            rm_disp_flg='N',
        )
        self.batch_line.log_sheet_flg = 'Y'
        self.batch_line.save(update_fields=['log_sheet_flg'])

        from django.urls import reverse
        url = reverse('transactions:log_sheet') + f'?edit_pk={logsheet.pk}'
        data = {
            'edit_pk': logsheet.pk,
            'gran_dt': '2025-05-13',
            'section': self.section.pk,
            'shift': LOGSHEET_SHIFT_NIGHT,
            'customer': self.customer.pk,
            'product': self.product.pk,
            'batch_dtl_id': self.batch_line.pk,
            'mfg_dt': 'MAY-2025',
            'exp_dt': 'APR-2028',
            'layer_slot': LOGSHEET_LAYER_SLOT_SINGLE,
        }
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)
        logsheet.refresh_from_db()
        self.assertEqual(logsheet.shift_id, LOGSHEET_SHIFT_NIGHT)
        self.assertEqual(logsheet.gran_dt, date(2025, 5, 13))
        self.batch_line.refresh_from_db()
        self.assertEqual(self.batch_line.log_sheet_flg, 'Y')

    def test_logsheet_delete_resets_batch_flag(self):
        from transactions.models import (
            LOGSHEET_LAYER_SLOT_SINGLE,
            LOGSHEET_SHIFT_DAY,
            TrnLogSheet,
        )
        logsheet = TrnLogSheet.objects.create(
            section=self.section,
            gran_dt=date(2025, 5, 12),
            customer=self.customer,
            shift_id=LOGSHEET_SHIFT_DAY,
            product=self.product,
            batch_line=self.batch_line,
            layer_slot=LOGSHEET_LAYER_SLOT_SINGLE,
            dpr_flg='N',
            rm_disp_flg='N',
        )
        self.batch_line.log_sheet_flg = 'Y'
        self.batch_line.save(update_fields=['log_sheet_flg'])

        from django.urls import reverse
        delete_url = reverse('transactions:log_sheet_delete', args=[logsheet.pk])
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TrnLogSheet.objects.filter(pk=logsheet.pk).exists())
        self.batch_line.refresh_from_db()
        self.assertEqual(self.batch_line.log_sheet_flg, 'N')


class InwardAndSalesOrderCustomerShortNameTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from masters.models import (
            FinancialYear,
            MstCust,
            MstProdCat,
            MstState,
            MstSupplier,
        )
        from transactions.models import TrnInwHed, TrnSlsOrdHed

        cls.user = get_user_model().objects.create_superuser('test_user', 'u@example.com', 'pass123')
        cls.fy = FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )
        cls.state = MstState.objects.create(state_name='Maharashtra ShortName', gst_code='27')
        cls.customer = MstCust.objects.create(
            cust_name='Aura Pharmaceuticals Pvt Ltd',
            short_name='AURA',
            address='Industrial Estate',
            state=cls.state,
            pin_code='400001',
        )
        cls.supplier = MstSupplier.objects.create(
            supl_name='Sigma Chemicals',
            short_name='SIGMA',
            address='Chemical Zone',
            state=cls.state,
            pin_code='400002',
        )
        cls.cat = MstProdCat.objects.create(prod_cat_id='RM', prod_cat_name='Raw Material')

        cls.inward = TrnInwHed.objects.create(
            inward_dt=date(2025, 5, 10),
            customer=cls.customer,
            register_no='R-88001',
            grn_category=cls.cat,
            grn_no='RM-88001',
            supplier=cls.supplier,
            inv_no='INV-88001',
            inv_dt=date(2025, 5, 9),
            financial_year=cls.fy,
            working_year='2025-26',
        )

        cls.sales_order = TrnSlsOrdHed.objects.create(
            ord_rec_dt=date(2025, 5, 10),
            customer=cls.customer,
            cust_ord_id='SO-88001',
            cust_ord_date=date(2025, 5, 9),
            financial_year=cls.fy,
            working_year='2025-26',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_inward_table_displays_customer_short_name(self):
        from django.urls import reverse
        resp = self.client.get(reverse('transactions:inward'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        # Check that the customer column in the inward table displays short_name with tooltip
        expected_cell = f'<td title="{self.customer.cust_name}">{self.customer.short_name}</td>'
        self.assertIn(expected_cell, content)

    def test_sales_order_table_displays_customer_short_name(self):
        from django.urls import reverse
        resp = self.client.get(reverse('transactions:sales_order'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        # Check that the customer column in the sales order table displays short_name with tooltip
        expected_cell = f'<td title="{self.customer.cust_name}">{self.customer.short_name}</td>'
        self.assertIn(expected_cell, content)


class DispensingAndSalesInvoiceCustomerShortNameTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from masters.models import (
            FinancialYear,
            MstBomRmHed,
            MstCust,
            MstCustProd,
            MstDepartment,
            MstItemType,
            MstMachine,
            MstPkgStyle,
            MstProd,
            MstProdCat,
            MstSection,
            MstState,
            MstTransport,
            MstUom,
        )
        from transactions.constants import GST_TYPE_EXEMPTED
        from transactions.models import (
            LOGSHEET_LAYER_SLOT_SINGLE,
            LOGSHEET_SHIFT_DAY,
            TrnBatchDtl,
            TrnBatchHed,
            TrnLogSheet,
            TrnlssHed,
            TrnSlsHed,
            TrnSlsOrdDtl1,
            TrnSlsOrdHed,
        )

        cls.user = get_user_model().objects.create_superuser('disp_si_admin', 'admin@example.com', 'adminpass')
        cls.fy = FinancialYear.objects.create(
            fy_start_year=2025,
            fy_end_year=2026,
            fy_display='2025-26',
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_current=True,
            is_open=True,
            is_closed=False,
        )
        cls.state = MstState.objects.create(state_name='Maharashtra Test', gst_code='27')
        cls.customer_with_short = MstCust.objects.create(
            cust_name='Aura Pharmaceuticals Pvt Ltd',
            short_name='AURA',
            address='123 Test Park',
            state=cls.state,
            pin_code='400001',
        )
        cls.customer_without_short = MstCust.objects.create(
            cust_name='Lyphochem Pharmaceutical',
            short_name='',
            address='456 Test Street',
            state=cls.state,
            pin_code='400002',
        )
        cls.transport = MstTransport.objects.create(transport_name='Test Express')
        cls.cat = MstProdCat.objects.create(prod_cat_id='TB', prod_cat_name='Tablet')
        cls.item_type = MstItemType.objects.create(item_type_name='Finished Good', item_category=cls.cat)
        cls.uom = MstUom.objects.create(uom_name='Tablet', short_name='TAB')
        cls.product = MstProd.objects.create(
            prod_name='Paracetamol 500mg',
            generic_name='Paracetamol',
            prod_type=cls.item_type,
            prod_category=cls.cat,
            uom=cls.uom,
            tablet_layer=MstProd.LAYER_SINGLE,
        )
        cls.dept = MstDepartment.objects.create(dept_name='Production')
        cls.section = MstSection.objects.create(section_name='Granulation-I', department=cls.dept)
        cls.machine = MstMachine.objects.create(machine_name='Machine 01', section=cls.section)
        cls.pkg_style = MstPkgStyle.objects.create(
            pkg_style_name='10x10 Blister',
            pkg_style_value=100,
            pkg_type=cls.item_type,
        )
        MstCustProd.objects.create(
            customer=cls.customer_with_short,
            product=cls.product,
            adv_license='N',
            batch_abbr='AUR',
        )
        cls.order = TrnSlsOrdHed.objects.create(
            ord_rec_dt=date(2025, 5, 10),
            customer=cls.customer_with_short,
            cust_ord_id='ORD-001',
            cust_ord_date=date(2025, 5, 10),
        )
        cls.order_line = TrnSlsOrdDtl1.objects.create(
            order=cls.order,
            product=cls.product,
            hsn_no='300490',
            packing_style=cls.pkg_style,
            order_qty=Decimal('100.00'),
            remaining_qty=Decimal('100.00'),
            ord_qty_nos=Decimal('100000'),
            rate=Decimal('1.50'),
            taxable_amt=Decimal('150.00'),
            gst_type=GST_TYPE_EXEMPTED,
            gst_per=Decimal('0.00'),
            prod_amt=Decimal('150.00'),
            export_type='DOMESTIC',
        )
        cls.batch_hed = TrnBatchHed.objects.create(
            customer=cls.customer_with_short,
            order=cls.order,
            order_line=cls.order_line,
            product=cls.product,
            batch_size_l=Decimal('1.00000'),
            batch_size_n=Decimal('100000'),
            batch_abbr='AUR',
            batch_from=1,
            batch_to=1,
        )
        cls.batch_line = TrnBatchDtl.objects.create(
            batch=cls.batch_hed,
            batch_no='AUR001',
            batch_qty_l=Decimal('1.00000'),
            batch_qty_n=Decimal('100000'),
            mfg_dt='MAY-2025',
            exp_dt='APR-2028',
            log_sheet_flg='Y',
        )
        cls.logsheet = TrnLogSheet.objects.create(
            section=cls.section,
            gran_dt=date(2025, 5, 12),
            customer=cls.customer_with_short,
            shift_id=LOGSHEET_SHIFT_DAY,
            product=cls.product,
            batch_line=cls.batch_line,
            layer_slot=LOGSHEET_LAYER_SLOT_SINGLE,
            dpr_flg='N',
            rm_disp_flg='N',
        )
        cls.bom_spec = MstBomRmHed.objects.create(
            spec_name='Paracetamol Spec',
            machine=cls.machine,
            customer=cls.customer_with_short,
            product=cls.product,
            no_of_lots=Decimal('1'),
            batch_size=Decimal('1.00'),
            batch_nos=100000,
        )
        cls.dispensing = TrnlssHed.objects.create(
            dispensing_dt=date(2025, 5, 12),
            customer=cls.customer_with_short,
            product=cls.product,
            batch_line=cls.logsheet,
            specification=cls.bom_spec,
            machine=cls.machine,
            lot_no=1,
            dispensed_by='Dispenser A',
            worker_name='Worker A',
        )
        cls.invoice_short = TrnSlsHed.objects.create(
            invoice_no='SI-00001',
            invoice_dt=date(2025, 5, 10),
            financial_year=cls.fy,
            working_year='2025-26',
            customer=cls.customer_with_short,
            transporter=cls.transport,
            delivery_add='123 Test Park',
            taxable_val=Decimal('1000.00'),
            total_amt=Decimal('1180.00'),
        )
        cls.invoice_no_short = TrnSlsHed.objects.create(
            invoice_no='SI-00002',
            invoice_dt=date(2025, 5, 11),
            financial_year=cls.fy,
            working_year='2025-26',
            customer=cls.customer_without_short,
            transporter=cls.transport,
            delivery_add='456 Test Street',
            taxable_val=Decimal('2000.00'),
            total_amt=Decimal('2360.00'),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_sales_invoice_table_displays_customer_short_name(self):
        from django.urls import reverse
        resp = self.client.get(reverse('transactions:sales_invoice'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        # Check that invoice with short_name shows short_name and full name tooltip
        expected_cell_short = f'<td title="{self.customer_with_short.cust_name}">{self.customer_with_short.short_name}</td>'
        self.assertIn(expected_cell_short, content)
        # Check that invoice without short_name falls back to cust_name
        expected_cell_fallback = f'<td title="{self.customer_without_short.cust_name}">{self.customer_without_short.cust_name}</td>'
        self.assertIn(expected_cell_fallback, content)

    def test_rm_dispensing_list_ajax_returns_customer_short_name(self):
        from django.urls import reverse
        resp = self.client.get(reverse('transactions:rm_dispensing_list_ajax'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('rows', data)
        self.assertTrue(len(data['rows']) >= 1)
        # Find dispensing row
        match = next((r for r in data['rows'] if r['dispensing_id'] == self.dispensing.pk), None)
        self.assertIsNotNone(match)
        self.assertEqual(match['customer'], 'AURA')
        self.assertEqual(match['customer_name'], 'Aura Pharmaceuticals Pvt Ltd')




