"""
dashboard/views.py

The main dashboard views and Director Transaction Command Center.
Provides high-performance, aggregated and itemized JSON endpoints for executive
reporting across all transaction modules:
- Inward / Goods Receipt Note (GRN - RM/PM)
- Granulation Logsheets
- Raw Material (RM) Dispensing
- Daily Production Reports (DPR)
- Contractor Daily Packaging (TrnPkgCont)
- Sales Orders & Fulfillment Tracking (TrnSlsOrdHed / Dtl1)
- Sales Invoices & Finished Goods Dispatches (TrnSlsHed)
- Live Central Stock Balances (StockHed)
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import render


@login_required
def dashboard_view(request):
    """
    Main dashboard page.
    Renders the executive Transaction Dashboard.
    """
    return render(request, 'dashboard/dashboard.html', {
        'page_title': "Transaction Command Center",
    })


@login_required
def director_dashboard_view(request):
    """Dashboard view alias for backwards compatibility."""
    return render(request, 'dashboard/dashboard.html', {
        'page_title': "Transaction Command Center",
    })


def _parse_date_range(request):
    """Parse from_date / to_date query params. Default: current month (1st to today)."""
    today = date.today()
    from_str = request.GET.get('from_date', '').strip()
    to_str = request.GET.get('to_date', '').strip()
    is_all = request.GET.get('all', '').strip().lower() in ('1', 'true', 'yes')

    if is_all:
        return date(2000, 1, 1), date(2099, 12, 31)

    try:
        from_dt = date.fromisoformat(from_str) if from_str else today.replace(day=1)
    except ValueError:
        from_dt = today.replace(day=1)
    try:
        to_dt = date.fromisoformat(to_str) if to_str else today
    except ValueError:
        to_dt = today

    # Safety: ensure chronological order
    if from_dt > to_dt:
        from_dt, to_dt = to_dt, from_dt

    return from_dt, to_dt


def _dec(val):
    """Convert Decimal/None to float for clean JSON serialization."""
    if val is None:
        return 0.0
    return float(val)


@login_required
def api_summary_kpis(request):
    """
    Consolidated executive KPI metrics across all transaction domains
    for the selected date period.
    """
    from transactions.models import (
        TrnInwHed,
        TrnLogSheet,
        TrnDpr,
        TrnlssHed,
        TrnPkgCont,
        TrnSlsOrdHed,
        TrnSlsOrdDtl1,
        TrnSlsHed,
    )
    from inventory.models import StockHed

    from_dt, to_dt = _parse_date_range(request)

    # Inward stats
    inwards_qs = TrnInwHed.objects.filter(inward_dt__range=(from_dt, to_dt))
    total_inwards = inwards_qs.count()
    total_grn_rm = inwards_qs.filter(grn_category_id='RM').count()
    total_grn_pm = inwards_qs.filter(grn_category_id='PM').count()
    total_inw_rm_qty = _dec(inwards_qs.filter(grn_category_id='RM').aggregate(qty=Sum('lines__quantity'))['qty'])
    total_inw_pm_qty = _dec(inwards_qs.filter(grn_category_id='PM').aggregate(qty=Sum('lines__quantity'))['qty'])

    # Granulation Logsheets
    logsheets_qs = TrnLogSheet.objects.filter(gran_dt__range=(from_dt, to_dt))
    total_logsheets = logsheets_qs.count()
    logsheets_dpr_done = logsheets_qs.filter(dpr_flg='Y').count()
    logsheets_disp_done = logsheets_qs.filter(rm_disp_flg='Y').count()

    # Daily Production Reports (DPR)
    dpr_qs = TrnDpr.objects.filter(trn_dpr_dt__range=(from_dt, to_dt))
    total_dpr = dpr_qs.count()
    dpr_working = dpr_qs.filter(machine_working='working').count()
    dpr_stoppage = dpr_qs.filter(machine_working='not_working').count()
    dpr_totals = dpr_qs.aggregate(total_kg=Sum('qty_kg'), total_nos=Sum('qty_nos'))
    total_prod_kg = _dec(dpr_totals['total_kg'])
    total_prod_nos = int(dpr_totals['total_nos'] or 0)

    # RM Dispensings
    total_rm_dispensings = TrnlssHed.objects.filter(dispensing_dt__range=(from_dt, to_dt)).count()

    # Contractor Packaging (TrnPkgCont)
    pkg_qs = TrnPkgCont.objects.filter(pkgcont_date__range=(from_dt, to_dt))
    total_packaging_entries = pkg_qs.count()
    pkg_totals = pkg_qs.aggregate(
        total_shippers=Sum('shipper_no'),
        total_packed_nos=Sum('qty_nos'),
        total_loose=Sum('qty_loose')
    )
    total_shippers = int(pkg_totals['total_shippers'] or 0)
    total_packed_nos = int(pkg_totals['total_packed_nos'] or 0)

    # Sales Orders & Order Fulfillment
    so_qs = TrnSlsOrdHed.objects.filter(ord_rec_dt__range=(from_dt, to_dt))
    total_sales_orders = so_qs.count()
    total_order_val = _dec(so_qs.aggregate(s=Sum('total_amt'))['s'])

    # Pending line fulfillment for this period
    so_lines_qs = TrnSlsOrdDtl1.objects.filter(order__ord_rec_dt__range=(from_dt, to_dt))
    pending_alloc_orders = so_lines_qs.filter(is_completed=False).count()
    pending_dispatch_orders = so_lines_qs.filter(is_sale_completed=False).count()

    # Sales Invoices & Dispatches
    sls_qs = TrnSlsHed.objects.filter(invoice_dt__range=(from_dt, to_dt))
    total_sales_invoices = sls_qs.count()
    total_invoice_amount = _dec(sls_qs.aggregate(s=Sum('total_amt'))['s'])

    # Live open stock rows monitored
    active_stock_batches = StockHed.objects.filter(is_closed=False).count()

    return JsonResponse({
        'total_inwards': total_inwards,
        'total_grn_rm': total_grn_rm,
        'total_grn_pm': total_grn_pm,
        'total_inw_rm_qty': total_inw_rm_qty,
        'total_inw_pm_qty': total_inw_pm_qty,
        'total_logsheets': total_logsheets,
        'logsheets_dpr_done': logsheets_dpr_done,
        'logsheets_disp_done': logsheets_disp_done,
        'total_dpr': total_dpr,
        'dpr_working': dpr_working,
        'dpr_stoppage': dpr_stoppage,
        'total_prod_kg': total_prod_kg,
        'total_prod_nos': total_prod_nos,
        'total_rm_dispensings': total_rm_dispensings,
        'total_packaging_entries': total_packaging_entries,
        'total_shippers': total_shippers,
        'total_packed_nos': total_packed_nos,
        'total_sales_orders': total_sales_orders,
        'total_order_val': total_order_val,
        'pending_alloc_orders': pending_alloc_orders,
        'pending_dispatch_orders': pending_dispatch_orders,
        'total_sales_invoices': total_sales_invoices,
        'total_invoice_amount': total_invoice_amount,
        'active_stock_batches': active_stock_batches,
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_inward_logsheet(request):
    """
    Inward / GRN logsheet data with comprehensive pharmaceutical details:
    Register No, GRN No, Category (RM/PM), Supplier, Customer, Invoice details,
    Transporter, Vehicle, Driver info, items count, received quantities, and batch ARNs.
    """
    from transactions.models import TrnInwHed

    from_dt, to_dt = _parse_date_range(request)

    qs = (
        TrnInwHed.objects
        .filter(inward_dt__range=(from_dt, to_dt))
        .select_related('supplier', 'customer', 'grn_category', 'transporter')
        .prefetch_related('batch_lines')
        .annotate(
            items_count=Count('lines', distinct=True),
            total_qty=Sum('lines__quantity'),
        )
        .order_by('-inward_dt', '-inward_id')
    )

    data = []
    for h in qs:
        # Collect batch numbers and ARN numbers (analytical report / COA reference)
        batches = []
        arns = []
        for b in h.batch_lines.all():
            if b.batch_no and b.batch_no not in batches:
                batches.append(b.batch_no)
            if b.arn_no and b.arn_no not in arns:
                arns.append(b.arn_no)

        data.append({
            'inward_id': h.inward_id,
            'inward_dt': h.inward_dt.isoformat() if h.inward_dt else '',
            'register_no': h.register_no or '',
            'grn_no': h.grn_no or '',
            'grn_category': str(h.grn_category_id) if h.grn_category_id else '',
            'supplier_name': h.supplier.supl_name if h.supplier else '—',
            'customer_name': h.customer.cust_name if h.customer else '—',
            'inv_no': h.inv_no or '—',
            'inv_dt': h.inv_dt.isoformat() if h.inv_dt else '',
            'vehicle_no': h.vehicle_no or '—',
            'transporter_name': h.transporter.transport_name if h.transporter else '—',
            'driver_name': h.driver_name or '',
            'driver_no': h.driver_no or '',
            'items_count': h.items_count or 0,
            'total_qty': _dec(h.total_qty),
            'uom': 'kg' if str(h.grn_category_id or '').upper() == 'RM' else 'Nos',
            'products_display': h.products_display or '',
            'batches_display': ', '.join(batches) if batches else '',
            'arns_display': ', '.join(arns) if arns else '',
            'has_doc': bool(h.documents),
            'remarks': h.remarks or '',
        })

    total_rm_qty = sum(Decimal(str(h.total_qty or 0)) for h in qs if str(h.grn_category_id or '').upper() == 'RM')
    total_pm_qty = sum(Decimal(str(h.total_qty or 0)) for h in qs if str(h.grn_category_id or '').upper() == 'PM')
    total_rm_lines = sum(h.items_count or 0 for h in qs if str(h.grn_category_id or '').upper() == 'RM')
    total_pm_lines = sum(h.items_count or 0 for h in qs if str(h.grn_category_id or '').upper() == 'PM')
    total_rm_count = sum(1 for h in qs if str(h.grn_category_id or '').upper() == 'RM')
    total_pm_count = sum(1 for h in qs if str(h.grn_category_id or '').upper() == 'PM')

    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'total_rm_qty': _dec(total_rm_qty),
        'total_pm_qty': _dec(total_pm_qty),
        'total_rm_lines': total_rm_lines,
        'total_pm_lines': total_pm_lines,
        'total_rm_count': total_rm_count,
        'total_pm_count': total_pm_count,
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_granulation_logsheet(request):
    """
    Granulation Logsheet transaction report:
    Logsheet No, Granulation Date, Shift, Section, Customer, Product,
    Batch No, Lacs & Nos sizes, Mfg Date, Expiry Date, Blending Date, Layer Slot,
    RM Dispensing flag, and DPR completed flag.
    """
    from transactions.models import TrnLogSheet

    from_dt, to_dt = _parse_date_range(request)

    qs = (
        TrnLogSheet.objects
        .filter(gran_dt__range=(from_dt, to_dt))
        .select_related('section', 'customer', 'product', 'batch_line', 'batch_line__batch')
        .order_by('-gran_dt', '-logsheet_id')
    )

    data = []
    for ls in qs:
        batch_no = ls.batch_line.batch_no if ls.batch_line else '—'
        batch_qty_l = _dec(ls.batch_line.batch_qty_l) if ls.batch_line else 0.0
        batch_qty_n = int(ls.batch_line.batch_qty_n or 0) if ls.batch_line else 0
        mfg_dt = ls.batch_line.mfg_dt if ls.batch_line else '—'
        exp_dt = ls.batch_line.exp_dt if ls.batch_line else '—'

        layer_label = {
            'S': 'Single Layer',
            '1': 'First Colour',
            '2': 'Second Colour',
        }.get(ls.layer_slot, ls.layer_slot)

        data.append({
            'logsheet_id': ls.logsheet_id,
            'gran_dt': ls.gran_dt.isoformat() if ls.gran_dt else '',
            'section_name': ls.section.section_name if ls.section else '—',
            'customer_name': ls.customer.cust_name if ls.customer else '—',
            'product_name': ls.product.prod_name if ls.product else '—',
            'batch_no': batch_no,
            'batch_qty_l': batch_qty_l,
            'batch_qty_n': batch_qty_n,
            'mfg_dt': mfg_dt,
            'exp_dt': exp_dt,
            'shift_id': ls.shift_id or '—',
            'blend_dt': ls.blend_dt.isoformat() if ls.blend_dt else '',
            'rm_disp_flg': ls.rm_disp_flg or 'N',
            'dpr_flg': ls.dpr_flg or 'N',
            'layer_slot': layer_label,
        })
    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_dpr_report(request):
    """
    Daily Production Report (DPR) data:
    Date, Section, Machine, Shift, Working Status, Product, Batch, Lot,
    Start/End Times, Total Time, Output (Kg & Nos), Section Yield,
    Primary/Secondary Operator, Helpers Count, and Stoppage/Supervision Remarks.
    """
    from transactions.models import TrnDpr

    from_dt, to_dt = _parse_date_range(request)

    qs = (
        TrnDpr.objects
        .filter(trn_dpr_dt__range=(from_dt, to_dt))
        .select_related('section', 'machine', 'customer', 'product', 'batch_line', 'operator1', 'operator2')
        .order_by('-trn_dpr_dt', '-trn_dpr_id')
    )

    data = []
    for d in qs:
        data.append({
            'trn_dpr_id': d.trn_dpr_id,
            'trn_dpr_dt': d.trn_dpr_dt.isoformat() if d.trn_dpr_dt else '',
            'section_name': d.section.section_name if d.section else '—',
            'machine_name': d.machine.machine_name if d.machine else '—',
            'shift_id': d.shift_id or '—',
            'customer_name': d.customer.cust_name if d.customer else '—',
            'product_name': d.product.prod_name if d.product else '—',
            'batch_no': d.batch_line.batch_no if d.batch_line else '—',
            'lot_no': d.lot_no or 0,
            'qty_kg': _dec(d.qty_kg),
            'qty_nos': d.qty_nos or 0,
            'section_qty': _dec(d.section_qty),
            'batch_size_lakh': _dec(d.batch_size_lakh),
            'start_time': str(d.start_time)[:5] if d.start_time else '—',
            'end_time': str(d.end_time)[:5] if d.end_time else '—',
            'total_time': d.total_time or '',
            'machine_working': d.machine_working or 'working',
            'operator1_name': d.operator1.opt_name if d.operator1 else '—',
            'operator2_name': d.operator2.opt_name if d.operator2 else '',
            'no_of_helper': d.no_of_helper or 0,
            'remarks': d.remarks or '',
        })
    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_rm_dispensing(request):
    """
    Raw Material Dispensing transaction report:
    Dispensing Date, Customer, Product, Batch, Formulation Specification,
    Machine, Lot No, Dispensed By, Worker, Checked By, Verified By,
    Item Lines count, and Total Dispensed Weight.
    """
    from transactions.models import TrnlssHed

    from_dt, to_dt = _parse_date_range(request)

    qs = (
        TrnlssHed.objects
        .filter(dispensing_dt__range=(from_dt, to_dt))
        .select_related('customer', 'product', 'batch_line', 'batch_line__batch_line', 'specification', 'machine')
        .annotate(
            lines_count=Count('lines', distinct=True),
            total_issue_qty=Sum('lines__issue_qty'),
            total_add_qty=Sum('lines__issue_add_qty'),
        )
        .order_by('-dispensing_dt', '-dispensing_id')
    )

    data = []
    for r in qs:
        batch_no = '—'
        if r.batch_line and r.batch_line.batch_line:
            batch_no = r.batch_line.batch_line.batch_no

        data.append({
            'dispensing_id': r.dispensing_id,
            'dispensing_dt': r.dispensing_dt.isoformat() if r.dispensing_dt else '',
            'customer_name': r.customer.cust_name if r.customer else '—',
            'product_name': r.product.prod_name if r.product else '—',
            'batch_no': batch_no,
            'spec_name': r.specification.spec_name if r.specification else '—',
            'machine_name': r.machine.machine_name if r.machine else '—',
            'lot_no': r.lot_no or 0,
            'dispensed_by': r.dispensed_by or '—',
            'worker_name': r.worker_name or '—',
            'checked_by': r.checked_by or '—',
            'verified_by': r.verified_by or '—',
            'lines_count': r.lines_count or 0,
            'total_dispensed_qty': _dec(r.total_issue_qty),
            'remarks': r.remarks or '',
        })
    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_packing_report(request):
    """
    Contractor Daily Packaging Register (TrnPkgCont):
    Packing Date, Contractor Name, Product, Customer, Log Sheet Batch,
    Packing Style (Alu-Alu, Blister, Strip, Bottle), Shipper Cartons,
    Packed Quantity Nos, Loose Qty, Manpower count, and Shift Remarks.
    """
    from transactions.models import TrnPkgCont

    from_dt, to_dt = _parse_date_range(request)

    qs = (
        TrnPkgCont.objects
        .filter(pkgcont_date__range=(from_dt, to_dt))
        .select_related(
            'contractor',
            'log_sheet',
            'log_sheet__customer',
            'log_sheet__product',
            'log_sheet__batch_line',
            'pkg_style'
        )
        .order_by('-pkgcont_date', '-pkgcont_id')
    )

    data = []
    for p in qs:
        batch_no = '—'
        product_name = '—'
        customer_name = '—'
        if p.log_sheet:
            if p.log_sheet.batch_line:
                batch_no = p.log_sheet.batch_line.batch_no
            if p.log_sheet.product:
                product_name = p.log_sheet.product.prod_name
            if p.log_sheet.customer:
                customer_name = p.log_sheet.customer.cust_name

        data.append({
            'pkgcont_id': p.pkgcont_id,
            'pkgcont_date': p.pkgcont_date.isoformat() if p.pkgcont_date else '',
            'contractor_name': p.contractor.opt_name if p.contractor else '—',
            'customer_name': customer_name,
            'product_name': product_name,
            'batch_no': batch_no,
            'pkg_style_name': p.pkg_style.pkg_style_name if p.pkg_style else '—',
            'shipper_no': p.shipper_no or 0,
            'qty_nos': int(p.qty_nos or 0),
            'qty_loose': int(p.qty_loose or 0),
            'no_of_girls': p.no_of_girls or 0,
            'remarks': p.remarks or '',
        })
    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_sales_orders(request):
    """
    Customer Sales Orders & Order Fulfillment Register (TrnSlsOrdHed / Dtl1):
    Order Date, Customer PO No, PO Date, Customer Name, Ordered Product,
    Packing Style, Order Qty (Lacs & Nos), Remaining Unallocated Qty,
    Allocation Status (Completed / Pending), Dispatch Status (Dispatched / Pending),
    Unit Rate, and Order Total Amount.
    """
    from transactions.models import TrnSlsOrdDtl1

    from_dt, to_dt = _parse_date_range(request)

    qs = (
        TrnSlsOrdDtl1.objects
        .filter(order__ord_rec_dt__range=(from_dt, to_dt))
        .select_related('order', 'order__customer', 'product', 'packing_style')
        .order_by('-order__ord_rec_dt', '-order_id', '-dtl1_id')
    )

    data = []
    for line in qs:
        hed = line.order
        data.append({
            'dtl1_id': line.dtl1_id,
            'order_id': hed.order_id,
            'ord_rec_dt': hed.ord_rec_dt.isoformat() if hed.ord_rec_dt else '',
            'cust_ord_id': hed.cust_ord_id or '—',
            'cust_ord_date': hed.cust_ord_date.isoformat() if hed.cust_ord_date else '',
            'customer_name': hed.customer.cust_name if hed.customer else '—',
            'product_name': line.product.prod_name if line.product else '—',
            'hsn_no': line.hsn_no or '',
            'pkg_style_name': line.packing_style.pkg_style_name if line.packing_style else '—',
            'order_qty': _dec(line.order_qty),
            'ord_qty_nos': int(line.ord_qty_nos or 0),
            'remaining_qty': _dec(line.remaining_qty),
            'rate': _dec(line.rate),
            'taxable_amt': _dec(line.taxable_amt),
            'total_amt': _dec(line.prod_amt),
            'is_completed': bool(line.is_completed),
            'is_sale_completed': bool(line.is_sale_completed),
        })
    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_sales_summary(request):
    """
    Sales invoice and finished goods dispatch report:
    Invoice No, Date, Customer, Reference Sales Order PO, Transporter,
    Delivery City/Address, Taxable Value, CGST, SGST, IGST, Total Amount,
    and Line Items count.
    """
    from transactions.models import TrnSlsHed

    from_dt, to_dt = _parse_date_range(request)

    qs = (
        TrnSlsHed.objects
        .filter(invoice_dt__range=(from_dt, to_dt))
        .select_related('customer', 'transporter', 'reference_order')
        .annotate(line_count=Count('lines', distinct=True))
        .order_by('-invoice_dt', '-invoice_id')
    )

    data = []
    for inv in qs:
        ref_po = inv.reference_order.cust_ord_id if inv.reference_order else '—'
        data.append({
            'invoice_id': inv.invoice_id,
            'invoice_no': inv.invoice_no or '—',
            'invoice_dt': inv.invoice_dt.isoformat() if inv.invoice_dt else '',
            'customer_name': inv.customer.cust_name if inv.customer else '—',
            'ref_po_no': ref_po,
            'transporter_name': inv.transporter.transport_name if inv.transporter else '—',
            'delivery_add': inv.delivery_add or '—',
            'taxable_val': _dec(inv.taxable_val),
            'cgst_amt': _dec(inv.cgst_amt),
            'sgst_amt': _dec(inv.sgst_amt),
            'igst_amt': _dec(inv.igst_amt),
            'freight_amt': _dec(inv.freight_amt),
            'total_amt': _dec(inv.total_amt),
            'line_count': inv.line_count or 0,
            'remarks': inv.remarks or '',
        })
    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'from_date': from_dt.isoformat(),
        'to_date': to_dt.isoformat(),
    })


@login_required
def api_stock_overview(request):
    """
    Central stock balance ledger overview with optional periodic movement filtering:
    Customer, Item Category (RM / PM / FG), Item/Product SKU, UOM, Batch No,
    Mfg Date, Exp Date, Opening Qty, Receipts, Issues, Available Closing Balance,
    and Last Transaction Date.
    Supports time period filtering (periodic movement) or live real-time balances.
    """
    from decimal import Decimal
    from inventory.models import StockHed
    from inventory.ledger_service import compute_periodic_stock_movements

    from_dt, to_dt = _parse_date_range(request)
    is_live = request.GET.get('live', '').strip().lower() in ('1', 'true', 'yes')
    is_all = request.GET.get('all', '').strip().lower() in ('1', 'true', 'yes')
    is_periodic = not is_live and not is_all and bool(request.GET.get('from_date') or request.GET.get('to_date'))

    qs = (
        StockHed.objects
        .filter(is_closed=False)
        .select_related(
            'customer',
            'product',
            'product__uom',
            'item',
            'item__uom',
            'item_category',
            'financial_year',
        )
        .order_by('customer__cust_name', 'item_category__prod_cat_name', 'product__prod_name', 'item__item_name')
    )

    all_hed_rows = list(qs)
    hed_ids = [s.pk for s in all_hed_rows]

    period_data = {}
    if is_periodic and hed_ids:
        period_data = compute_periodic_stock_movements(hed_ids, from_date=from_dt, to_date=to_dt)

    data = []
    totals = {
        'RM': {'opn': Decimal('0'), 'rcpt': Decimal('0'), 'issue': Decimal('0'), 'closing': Decimal('0'), 'count': 0},
        'PM': {'opn': Decimal('0'), 'rcpt': Decimal('0'), 'issue': Decimal('0'), 'closing': Decimal('0'), 'count': 0},
        'FG': {'opn': Decimal('0'), 'rcpt': Decimal('0'), 'issue': Decimal('0'), 'closing': Decimal('0'), 'count': 0},
        'ALL': {'opn': Decimal('0'), 'rcpt': Decimal('0'), 'issue': Decimal('0'), 'closing': Decimal('0'), 'count': 0},
    }

    for s in all_hed_rows:
        sku_name = ''
        sku_type = 'RM'
        uom_str = ''

        if s.product:
            sku_name = s.product.prod_name
            sku_type = 'FG'
            if s.product.uom:
                uom_str = s.product.uom.short_name or s.product.uom.uom_name
            else:
                uom_str = 'Nos'
        elif s.item:
            sku_name = s.item.item_name
            sku_type = 'RM' if str(s.item_category_id or '').upper() == 'RM' else 'PM'
            if s.item.uom:
                uom_str = s.item.uom.short_name or s.item.uom.uom_name
            else:
                uom_str = 'kg' if sku_type == 'RM' else 'Nos'

        cat_code = str(s.item_category_id or sku_type).upper()
        if cat_code not in ('RM', 'PM', 'FG'):
            cat_code = sku_type

        if is_periodic and s.pk in period_data:
            mv = period_data[s.pk]
            opn = mv.get('opening_qty', Decimal('0'))
            rcpt = mv.get('receipt_qty', Decimal('0'))
            issue = mv.get('issue_qty', Decimal('0'))
            closing = mv.get('closing_qty', Decimal('0'))
        else:
            opn = s.opn_qty or Decimal('0')
            rcpt = s.rcpt_qty or Decimal('0')
            issue = s.issue_qty or Decimal('0')
            closing = s.closing_qty or Decimal('0')

        if cat_code in totals:
            totals[cat_code]['opn'] += opn
            totals[cat_code]['rcpt'] += rcpt
            totals[cat_code]['issue'] += issue
            totals[cat_code]['closing'] += closing
            totals[cat_code]['count'] += 1

        totals['ALL']['opn'] += opn
        totals['ALL']['rcpt'] += rcpt
        totals['ALL']['issue'] += issue
        totals['ALL']['closing'] += closing
        totals['ALL']['count'] += 1

        data.append({
            'customer_name': s.customer.cust_name if s.customer else '—',
            'category': s.item_category.prod_cat_name if s.item_category else sku_type,
            'category_code': cat_code,
            'sku_name': sku_name,
            'uom': uom_str or '—',
            'batch_no': s.batch_no or '—',
            'mfg_date': s.mfg_date.isoformat() if s.mfg_date else '—',
            'exp_date': s.exp_date.isoformat() if s.exp_date else '—',
            'opn_qty': _dec(opn),
            'rcpt_qty': _dec(rcpt),
            'issue_qty': _dec(issue),
            'closing_qty': _dec(closing),
            'last_trn_date': s.last_trn_date.isoformat() if s.last_trn_date else '—',
        })

    return JsonResponse({
        'data': data,
        'total_records': len(data),
        'is_periodic': is_periodic,
        'from_date': from_dt.isoformat() if is_periodic else '',
        'to_date': to_dt.isoformat() if is_periodic else '',
        'totals': {
            k: {
                'opn': _dec(v['opn']),
                'rcpt': _dec(v['rcpt']),
                'issue': _dec(v['issue']),
                'closing': _dec(v['closing']),
                'count': v['count'],
            } for k, v in totals.items()
        }
    })
