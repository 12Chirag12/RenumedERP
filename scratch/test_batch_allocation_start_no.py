import os
import sys
from decimal import Decimal
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from django.db import transaction
from masters.models import MstCust, MstProd, MstCustProd, MstPkgStyle
from transactions.models import TrnSlsOrdHed, TrnSlsOrdDtl1, TrnBatchHed, TrnBatchDtl
from transactions.forms import BatchAllocationForm

def run_tests():
    print("=" * 60)
    print("RUNNING BATCH ALLOCATION 'BATCH START NO.' COMPREHENSIVE TESTS")
    print("=" * 60)

    with transaction.atomic():
        cust = MstCust.objects.first()
        prod_a = MstProd.objects.first()
        prods = list(MstProd.objects.filter(prod_type=prod_a.prod_type)[:4])
        while len(prods) < 4:
            prods.append(MstProd.objects.create(
                prod_name=f"Test Prod {len(prods)}",
                prod_type=prod_a.prod_type,
                generic_name="Generic",
                uom=prod_a.uom,
                hsn_code=prod_a.hsn_code,
            ))
        prod_a, prod_b, prod_c, prod_d = prods[0], prods[1], prods[2], prods[3]

        pkg_style, _ = MstPkgStyle.objects.get_or_create(
            pkg_style_name="TEST 1X1",
            defaults={'pkg_style_value': 1, 'pkg_type': prod_a.prod_type}
        )

        # Setup batch abbreviations
        MstCustProd.objects.update_or_create(customer=cust, product=prod_a, defaults={'batch_abbr': 'TPA'})
        MstCustProd.objects.update_or_create(customer=cust, product=prod_b, defaults={'batch_abbr': 'TPB'})
        MstCustProd.objects.update_or_create(customer=cust, product=prod_c, defaults={'batch_abbr': 'TPC'})
        MstCustProd.objects.update_or_create(customer=cust, product=prod_d, defaults={'batch_abbr': 'TPD'})

        # Clean any preexisting test batch lines with these abbreviations in case
        TrnBatchDtl.objects.filter(batch_no__startswith='TPA').delete()
        TrnBatchDtl.objects.filter(batch_no__startswith='TPB').delete()
        TrnBatchDtl.objects.filter(batch_no__startswith='TPC').delete()
        TrnBatchDtl.objects.filter(batch_no__startswith='TPD').delete()

        # Create Sales Order
        order = TrnSlsOrdHed.objects.create(
            customer=cust,
            cust_ord_id="TEST-SO-001",
            cust_ord_date=datetime.date(2026, 5, 1),
            ord_rec_dt=datetime.date(2026, 5, 1),
        )

        # -------------------------------------------------------------
        # Test 22 Acceptance Test & Test L (Partial/Loose Batch)
        # Product A: 550,000 tablets, Per Batch Size: 1 Lacs (100,000), Batch Start No: 1
        # Expect: TPA1..TPA5 (100,000 each), TPA6 (50,000 partial)
        # -------------------------------------------------------------
        line_a = TrnSlsOrdDtl1.objects.create(
            order=order,
            product=prod_a,
            packing_style=pkg_style,
            order_qty=Decimal('5.50'),
            ord_qty_nos=Decimal('550000'),
            remaining_qty=Decimal('5.50'),
            rate=Decimal('10.00'),
            hsn_no='3004',
            gst_type='CGST_SGST',
            gst_per=Decimal('12.00'),
            export_type='domestic',
        )
        assert line_a.no_of_tablets == Decimal('550000')

        form_data_a = {
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_a.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 1,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        }
        form_a = BatchAllocationForm(data=form_data_a)
        assert form_a.is_valid(), f"Form A validation failed: {form_a.errors}"
        hed_a = form_a.save()
        batches_a = list(hed_a.lines.all().order_by('dtl_id'))
        print(f"[PASS] Section 22 / Test L: Product A generated {len(batches_a)} batches.")
        assert len(batches_a) == 6
        assert hed_a.batch_from == 1
        assert hed_a.batch_to == 6
        assert hed_a.batch_start_no == 1
        expected_a = [
            ('TPA1', Decimal('100000')),
            ('TPA2', Decimal('100000')),
            ('TPA3', Decimal('100000')),
            ('TPA4', Decimal('100000')),
            ('TPA5', Decimal('100000')),
            ('TPA6', Decimal('50000')), # Partial/loose batch
        ]
        for b, (exp_no, exp_qty) in zip(batches_a, expected_a):
            assert b.batch_no == exp_no, f"Expected {exp_no}, got {b.batch_no}"
            assert b.batch_qty_n == exp_qty, f"Expected {exp_qty}, got {b.batch_qty_n}"
            print(f"   {b.batch_no} -> {b.batch_qty_n} Nos ({b.batch_qty_l} Lacs)")

        # -------------------------------------------------------------
        # Section 22 / Test K (Exact Division) & Test B (Multiple Products with Independent Start No)
        # Product B: 300,000 tablets, Batch Size: 100,000, Batch Start No: 20
        # Expect: TPB20, TPB21, TPB22 (100,000 each). MUST NOT start from 7!
        # -------------------------------------------------------------
        line_b = TrnSlsOrdDtl1.objects.create(
            order=order,
            product=prod_b,
            packing_style=pkg_style,
            order_qty=Decimal('3.00'),
            ord_qty_nos=Decimal('300000'),
            remaining_qty=Decimal('3.00'),
            rate=Decimal('10.00'),
            hsn_no='3004',
            gst_type='CGST_SGST',
            gst_per=Decimal('12.00'),
            export_type='domestic',
        )
        assert line_b.no_of_tablets == Decimal('300000')

        form_data_b = {
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_b.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 20,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        }
        form_b = BatchAllocationForm(data=form_data_b)
        assert form_b.is_valid(), f"Form B validation failed: {form_b.errors}"
        hed_b = form_b.save()
        batches_b = list(hed_b.lines.all().order_by('dtl_id'))
        print(f"[PASS] Section 22 / Test B & K: Product B generated {len(batches_b)} batches.")
        assert len(batches_b) == 3
        assert hed_b.batch_from == 20
        assert hed_b.batch_to == 22
        assert hed_b.batch_start_no == 20
        expected_b = [
            ('TPB20', Decimal('100000')),
            ('TPB21', Decimal('100000')),
            ('TPB22', Decimal('100000')),
        ]
        for b, (exp_no, exp_qty) in zip(batches_b, expected_b):
            assert b.batch_no == exp_no, f"Expected {exp_no}, got {b.batch_no}"
            assert b.batch_qty_n == exp_qty, f"Expected {exp_qty}, got {b.batch_qty_n}"
            print(f"   {b.batch_no} -> {b.batch_qty_n} Nos ({b.batch_qty_l} Lacs)")

        # -------------------------------------------------------------
        # Test C: Third Product with Batch Start No = 50
        # Product C: 200,000 tablets, Batch Size: 100,000, Start No: 50 -> TPC50, TPC51
        # -------------------------------------------------------------
        line_c = TrnSlsOrdDtl1.objects.create(
            order=order,
            product=prod_c,
            packing_style=pkg_style,
            order_qty=Decimal('2.00'),
            ord_qty_nos=Decimal('200000'),
            remaining_qty=Decimal('2.00'),
            rate=Decimal('10.00'),
            hsn_no='3004',
            gst_type='CGST_SGST',
            gst_per=Decimal('12.00'),
            export_type='domestic',
        )
        assert line_c.no_of_tablets == Decimal('200000')

        form_data_c = {
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_c.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 50,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        }
        form_c = BatchAllocationForm(data=form_data_c)
        assert form_c.is_valid(), f"Form C validation failed: {form_c.errors}"
        hed_c = form_c.save()
        batches_c = list(hed_c.lines.all().order_by('dtl_id'))
        print(f"[PASS] Test C: Product C generated {len(batches_c)} batches (TPC50, TPC51).")
        assert [b.batch_no for b in batches_c] == ['TPC50', 'TPC51']

        # -------------------------------------------------------------
        # Test D: Delete the middle product (Product B)
        # Expected: Product A and Product C remain completely unchanged!
        # -------------------------------------------------------------
        line_b.delete() # Deletes line_b (and its batch header via CASCADE)
        assert TrnBatchHed.objects.filter(pk=hed_a.pk).exists()
        assert TrnBatchHed.objects.filter(pk=hed_c.pk).exists()
        batches_a_after = [b.batch_no for b in hed_a.lines.all().order_by('dtl_id')]
        batches_c_after = [b.batch_no for b in hed_c.lines.all().order_by('dtl_id')]
        assert batches_a_after == ['TPA1', 'TPA2', 'TPA3', 'TPA4', 'TPA5', 'TPA6']
        assert batches_c_after == ['TPC50', 'TPC51']
        # -------------------------------------------------------------
        # Test H: Change Batch Start No for one product (e.g. from 50 to 60)
        # -------------------------------------------------------------
        line_h = TrnSlsOrdDtl1.objects.create(
            order=order,
            product=prod_c,
            packing_style=pkg_style,
            order_qty=Decimal('2.00'),
            ord_qty_nos=Decimal('200000'),
            remaining_qty=Decimal('2.00'),
            rate=Decimal('15.00'),
            hsn_no='3004',
            gst_type='CGST_SGST',
            gst_per=Decimal('12.00'),
            export_type='domestic',
        )
        form_h_before = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_h.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 5,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert form_h_before.is_valid()
        assert [l['batch_no'] for l in form_h_before.cleaned_data['_save_context']['lines']] == ['TPC5', 'TPC6']

        # Change start no to 10
        form_h_after = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_h.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 10,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert form_h_after.is_valid()
        assert [l['batch_no'] for l in form_h_after.cleaned_data['_save_context']['lines']] == ['TPC10', 'TPC11']
        print("[PASS] Test H: Changing Batch Start No from 5 to 10 regenerated batches TPC10, TPC11.")

        # -------------------------------------------------------------
        # Test I: Change Per Batch Size for one product
        # 200,000 tablets with batch size 0.5 Lacs (50,000) -> 4 batches
        # -------------------------------------------------------------
        form_i = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_h.pk,
            'batch_size_l': '0.50',
            'batch_start_no': 10,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert form_i.is_valid()
        lines_i = form_i.cleaned_data['_save_context']['lines']
        assert len(lines_i) == 4
        assert [l['batch_no'] for l in lines_i] == ['TPC10', 'TPC11', 'TPC12', 'TPC13']
        assert [l['batch_qty_n'] for l in lines_i] == [Decimal('50000')] * 4
        print("[PASS] Test I: Changed Per Batch Size to 0.5 Lacs -> generated 4 batches of 50,000 Nos.")

        # -------------------------------------------------------------
        # Test J: Change No. of Tablets / Quantity
        # Update line_h quantity from 200,000 to 150,000
        # -------------------------------------------------------------
        line_h.order_qty = Decimal('1.50')
        line_h.ord_qty_nos = Decimal('150000')
        line_h.remaining_qty = Decimal('1.50')
        line_h.save()
        form_j = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_h.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 10,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert form_j.is_valid()
        lines_j = form_j.cleaned_data['_save_context']['lines']
        assert len(lines_j) == 2
        assert lines_j[0]['batch_qty_n'] == Decimal('100000')
        assert lines_j[1]['batch_qty_n'] == Decimal('50000')
        print("[PASS] Test J: Changed Quantity to 150,000 -> 1 full batch (100k) + 1 loose batch (50k).")

        # -------------------------------------------------------------
        # Test G: Add Product D after deleting Product B
        # Enter separate Batch Start No = 75 for Product D
        # Expected: Product A keeps its batches, Product C keeps its batches, Product D uses 75.
        # -------------------------------------------------------------
        line_d = TrnSlsOrdDtl1.objects.create(
            order=order,
            product=prod_d,
            packing_style=pkg_style,
            order_qty=Decimal('1.00'),
            ord_qty_nos=Decimal('100000'),
            remaining_qty=Decimal('1.00'),
            rate=Decimal('10.00'),
            hsn_no='3004',
            gst_type='CGST_SGST',
            gst_per=Decimal('12.00'),
            export_type='domestic',
        )
        form_data_d = {
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_d.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 75,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        }
        form_d = BatchAllocationForm(data=form_data_d)
        assert form_d.is_valid()
        hed_d = form_d.save()
        batches_d = [b.batch_no for b in hed_d.lines.all()]
        assert batches_d == ['TPD75']
        # Verify A and C
        assert [b.batch_no for b in hed_a.lines.all().order_by('dtl_id')] == ['TPA1', 'TPA2', 'TPA3', 'TPA4', 'TPA5', 'TPA6']
        assert [b.batch_no for b in hed_c.lines.all().order_by('dtl_id')] == ['TPC50', 'TPC51']
        print(f"[PASS] Test G: Added Product D (TPD75). Neither A nor C was renumbered!")

        # -------------------------------------------------------------
        # Test 10: Duplicate Batch Validation
        # TPD75 already exists. Try allocating line with Batch Start No = 75 again.
        # Expect: Validation error on batch_start_no: "Generated batch number already exists."
        # -------------------------------------------------------------
        line_d2 = TrnSlsOrdDtl1.objects.create(
            order=order,
            product=prod_d,
            packing_style=pkg_style,
            order_qty=Decimal('1.00'),
            ord_qty_nos=Decimal('100000'),
            remaining_qty=Decimal('1.00'),
            rate=Decimal('12.00'),
            hsn_no='3004',
            gst_type='CGST_SGST',
            gst_per=Decimal('12.00'),
            export_type='domestic',
        )
        form_dup = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_d2.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 75,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert not form_dup.is_valid()
        assert 'batch_start_no' in form_dup.errors
        assert 'Generated batch number already exists' in form_dup.errors['batch_start_no'][0]
        print(f"[PASS] Test 10: Duplicate batch number TPD75 prevented with error: {form_dup.errors['batch_start_no'][0]}")

        # -------------------------------------------------------------
        # Test 20: Validation for Invalid / Non-positive Batch Start No
        # -------------------------------------------------------------
        form_inv1 = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_d2.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 0,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert not form_inv1.is_valid()
        assert 'batch_start_no' in form_inv1.errors
        print(f"[PASS] Test 20: Batch Start No = 0 rejected: {form_inv1.errors['batch_start_no'][0]}")

        form_inv2 = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_d2.pk,
            'batch_size_l': '1.00',
            'batch_start_no': -5,
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert not form_inv2.is_valid()
        assert 'batch_start_no' in form_inv2.errors
        print(f"[PASS] Test 20: Batch Start No = -5 rejected: {form_inv2.errors['batch_start_no'][0]}")

        form_inv3 = BatchAllocationForm(data={
            'customer': cust.pk,
            'order_id': order.pk,
            'order_line_id': line_d2.pk,
            'batch_size_l': '1.00',
            'batch_start_no': 'abc',
            'mfg_dt': '2026-05',
            'exp_dt': '2028-05',
        })
        assert not form_inv3.is_valid()
        assert 'batch_start_no' in form_inv3.errors
        print(f"[PASS] Test 20: Batch Start No = 'abc' rejected: {form_inv3.errors['batch_start_no'][0]}")

        # -------------------------------------------------------------
        # Test M, N, O: Reopen, inspect persistence and product associations
        # -------------------------------------------------------------
        hed_c_reopen = TrnBatchHed.objects.get(pk=hed_c.pk)
        assert hed_c_reopen.batch_from == 50
        assert hed_c_reopen.batch_start_no == 50
        assert hed_c_reopen.batch_to == 51
        assert hed_c_reopen.product == prod_c
        assert hed_c_reopen.order_line == line_c
        c_lines = list(hed_c_reopen.lines.all().order_by('dtl_id'))
        assert [b.batch_no for b in c_lines] == ['TPC50', 'TPC51']
        for b in c_lines:
            assert b.batch.product == prod_c
        print("[PASS] Test M, N, O: Reopening batch allocations verifies correct product association, batch numbers, and batch_start_no.")

        # Rollback transaction so test data is discarded
        transaction.set_rollback(True)

    print("=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()
