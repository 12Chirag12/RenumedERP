"""
transactions/views.py

════════════════════════════════════════════════════════════════
 FORM CONTRACT  (same idea as masters/views.py)
════════════════════════════════════════════════════════════════
InwardForm in ``transactions.forms`` implements:

    get_initial(self) -> dict
        Default inward date for new records; header snapshot when editing.

    save(self) -> TrnInwHed
        Atomic create of header + TrnInwDtl1 + TrnInwDtl2 rows.

Infrastructure mirrors masters: get_instance() for ?edit_pk= lookups.
════════════════════════════════════════════════════════════════
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Prefetch, Sum
from django.db.models.deletion import ProtectedError
from django import forms as django_forms
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views import View
from django.utils import timezone
from datetime import timedelta

from django.utils.dateparse import parse_date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from masters.models import (
    MstBomRmDtl,
    MstBomRmHed,
    MstCustProd,
    MstItem,
    MstMachine,
    MstOperator,
    MstPkgStyle,
    MstProd,
    MstProdCat,
    MstSection,
)
from masters.views import delete_object

from inventory.models import InventoryStock
from inventory.transaction_posting import reverse_inward_from_inventory, reverse_sales_invoice_from_inventory

from .constants import GRN_CATEGORY_IDS
from .forms import (
    BatchAllocationForm,
    DprForm,
    InwardForm,
    LogSheetForm,
    PkgContForm,
    RmDispensingForm,
    SalesInvoiceForm,
    SalesOrderForm,
)
from .forms._constants import _SO_QTY_QUANTIZE
from .forms.sales_invoice import refresh_order_line_sale_completed
from .forms.shared_utils import dpr_is_multi_batch_section
from .models import (
    DPR_MACHINE_WORKING,
    LOGSHEET_LAYER_SLOT_FIRST,
    LOGSHEET_LAYER_SLOT_SECOND,
    LOGSHEET_LAYER_SLOT_SINGLE,
    LOGSHEET_SHIFT_DAY,
    LOGSHEET_SHIFT_NIGHT,
    TrnBatchDtl,
    TrnDpr,
    TrnDprInputBatch,
    TrnInwDtl1,
    TrnInwDtl2,
    TrnInwHed,
    TrnLogSheet,
    TrnPkgCont,
    TrnSlsDtl1,
    TrnSlsDtl2,
    TrnSlsHed,
    TrnSlsOrdDtl1,
    TrnSlsOrdDtl2,
    TrnSlsOrdHed,
    TrnlssHed,
    TrnlssDtl,
    logsheet_split_batch_qty,
)
from .numbering import max_grn_sequence, suggested_register_no, max_grn_sequence_for_fy, suggested_grn_no, suggested_sales_invoice_no, max_invoice_sequence_for_fy
from .utils import get_or_create_financial_year_for_date


def get_instance(model, pk):
    """Return get_object_or_404(model, pk=pk) when pk is truthy, else None."""
    return get_object_or_404(model, pk=pk) if pk else None


def get_inward_edit_instance(pk):
    """
    Load TrnInwHed with header FKs plus all TrnInwDtl1 and TrnInwDtl2 rows
    for edit — same pattern as masters combined views (full snapshot for form.get_initial).
    """
    if not pk:
        return None
    lines_qs = TrnInwDtl1.objects.select_related('item', 'uom').order_by('dtl1_id')
    batches_qs = TrnInwDtl2.objects.select_related('product').order_by('dtl2_id')
    return get_object_or_404(
        TrnInwHed.objects.select_related(
            'customer', 'supplier', 'grn_category', 'transporter',
        ).prefetch_related(
            Prefetch('lines', queryset=lines_qs),
            Prefetch('batch_lines', queryset=batches_qs),
        ),
        pk=pk,
    )


def _inward_recent_queryset():
    return (
        TrnInwHed.objects.select_related(
            'customer', 'supplier', 'grn_category', 'transporter',
        )
        .order_by('-inward_id')[:40]
    )


def _inward_master_payload():
    products = list(
        MstProd.objects.order_by('prod_name').values('prod_id', 'prod_name')
    )
    grn_categories = list(
        MstProdCat.objects.filter(prod_cat_id__in=GRN_CATEGORY_IDS)
        .order_by('prod_cat_name')
        .values('prod_cat_id', 'prod_cat_name')
    )
    return {'products': products, 'grn_categories': grn_categories}


def _inward_ajax_urls():
    """Resolved paths for fetch() — avoids hard-coded URLs and SCRIPT_NAME issues."""
    return {
        'items': reverse('transactions:inward_items_ajax'),
        'itemMeta': reverse('transactions:inward_item_meta_ajax'),
        'nextNumbers': reverse('transactions:inward_next_numbers_ajax'),
        'suggestGrn': reverse('transactions:suggest_grn_api'),
    }


def _inward_number_suggest_payload():
    """Suggested next register / shared GRN sequence for new inward forms and client reset."""
    fy = get_or_create_financial_year_for_date(timezone.localdate())
    wy = fy.fy_display if fy else ''
    return {
        'register_no': suggested_register_no(),
        # Backward compatible field used by existing JS; now scoped per FY (working_year).
        'grn_seq': max_grn_sequence_for_fy(wy) + 1,
        'working_year': wy,
    }


@login_required
def inward_view(request):
    """
    GET  — blank form (default inward date) or edit snapshot when ?edit_pk= is set.
    POST — validate and save; re-render with errors on failure.
    """
    edit_pk = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_inward_edit_instance(edit_pk) if edit_pk else None

    start_step = 1

    if request.method == 'POST':
        form = InwardForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            try:
                hed = form.save()
            except ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
            else:
                messages.success(
                    request,
                    f'Inward {"updated" if instance else "saved"} successfully. Internal ID {hed.inward_id}, GRN {hed.grn_no}.',
                )
                return redirect('transactions:inward')
        else:
            if 'lines_json' in form.errors:
                start_step = 2
    else:
        form = InwardForm(instance=instance)
        if instance:
            form.initial = form.get_initial()
        else:
            form.initial = {**form.get_initial(), **(form.initial or {})}

    inward_page_data = {
        'startStep': start_step,
        'isEdit': bool(instance),
        'numberSuggest': _inward_number_suggest_payload(),
    }
    ctx = {
        'form': form,
        'recent': _inward_recent_queryset(),
        'edit_instance': instance,
        'start_step': start_step,
        'inward_ajax_urls': _inward_ajax_urls(),
        'inward_page_data': inward_page_data,
        **_inward_master_payload(),
    }
    return render(request, 'transactions/inward_form.html', ctx)


@login_required
def inward_delete_view(request, pk):
    if request.method != 'POST':
        return redirect('transactions:inward')
    hed = get_object_or_404(
        TrnInwHed.objects.select_related('financial_year').prefetch_related(
            'lines__item',
            'batch_lines',
        ),
        pk=pk,
    )
    fy = hed.financial_year
    if fy is not None and (not fy.is_open or fy.is_closed):
        messages.error(
            request,
            f'Cannot delete inward in a closed financial year ({fy.fy_display}).',
        )
        return redirect('transactions:inward')
    name = hed.grn_no
    try:
        with transaction.atomic():
            reverse_inward_from_inventory(hed)
            hed.delete()
        messages.success(request, f'"{name}" deleted successfully.')
    except ProtectedError as e:
        blocking = ', '.join(sorted({rel.__class__.__name__ for rel in e.protected_objects}))
        messages.error(
            request,
            f'Cannot delete "{name}" — it is referenced by: {blocking}.',
        )
    return redirect('transactions:inward')


@login_required
@require_GET
def inward_items_ajax(request):
    """Items filtered by GRN category (RM / PM) — matches MstItem.item_category."""
    cat = (request.GET.get('grn_cat') or '').strip().upper()
    if cat not in GRN_CATEGORY_IDS:
        return JsonResponse({'items': [], 'error': 'Invalid grn_cat'}, status=400)
    items = list(
        MstItem.objects.filter(item_category_id=cat)
        .order_by('item_name')
        .values('item_id', 'item_name')
    )
    return JsonResponse({'items': items})


@login_required
@require_GET
def inward_next_numbers_ajax(request):
    """Latest suggested register no. and shared GRN sequence (for form reset / client sync)."""
    p = _inward_number_suggest_payload()
    return JsonResponse(p)


@login_required
@require_GET
def inward_item_meta_ajax(request):
    try:
        pk = int(request.GET.get('item_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid item_id'}, status=400)
    try:
        item = MstItem.objects.select_related('uom', 'item_type').get(pk=pk)
    except MstItem.DoesNotExist:
        return JsonResponse({'error': 'Item not found'}, status=404)

    return JsonResponse({
        'item_id': item.pk,
        'maintain_batch': item.maintain_batch == 'Y',
        'uom_id': item.uom_id,
        'uom_name': item.uom.short_name if item.uom else '',
        'item_type_id': item.item_type_id,
        'mfg_date_enabled': item.mfg_date == 'Y',
        'exp_date_enabled': item.exp_date == 'Y',
        'last_purchase_rate': str(item.last_purchase_rate),
    })


class SuggestGRNView(View):
    """
    API: suggest next GRN number scoped by working_year.

    Query params:
      - grn_category_id: "RM" | "PM" (required)
      - inward_dt: "YYYY-MM-DD" (optional; used to derive FY)
      - working_year: "2025-26" (optional fallback if inward_dt omitted)
    """

    def get(self, request):
        gid = (request.GET.get('grn_category_id') or '').strip().upper()
        inward_dt_raw = (request.GET.get('inward_dt') or '').strip()
        wy = (request.GET.get('working_year') or '').strip()

        if gid not in GRN_CATEGORY_IDS:
            return JsonResponse({'error': 'Invalid grn_category_id'}, status=400)

        if inward_dt_raw:
            d = parse_date(inward_dt_raw)
            if not d:
                return JsonResponse({'error': 'Invalid inward_dt'}, status=400)
            fy = get_or_create_financial_year_for_date(d)
            wy = fy.fy_display if fy else ''
        else:
            wy = wy or (get_or_create_financial_year_for_date(timezone.localdate()).fy_display)

        seq = max_grn_sequence_for_fy(wy) + 1
        return JsonResponse({
            'working_year': wy,
            'grn_seq': seq,
            'grn_no': suggested_grn_no(gid, wy),
        })


def get_sales_order_edit_instance(pk):
    if not pk:
        return None
    lines_qs = TrnSlsOrdDtl1.objects.select_related('product', 'packing_style').order_by('dtl1_id')
    disp_qs = TrnSlsOrdDtl2.objects.select_related('product').order_by('disp_sche_dt', 'dtl2_id')
    return get_object_or_404(
        TrnSlsOrdHed.objects.select_related('customer', 'financial_year').prefetch_related(
            Prefetch('lines', queryset=lines_qs),
            Prefetch('dispatch_lines', queryset=disp_qs),
        ),
        pk=pk,
    )


def _sales_order_recent_queryset():
    return (
        TrnSlsOrdHed.objects.select_related('customer')
        .order_by('-order_id')[:40]
    )


def _sales_order_products_payload():
    # Product dropdown is now customer-filtered via AJAX; keep empty payload for initial render.
    return []


def _sales_order_ajax_urls():
    return {
        'productMeta': reverse('transactions:sales_order_product_meta_ajax'),
        'customerProducts': reverse('transactions:sales_order_customer_products_ajax'),
    }


@login_required
def sales_order_view(request):
    edit_pk = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_sales_order_edit_instance(edit_pk) if edit_pk else None
    start_step = 1

    if request.method == 'POST':
        form = SalesOrderForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            try:
                hed = form.save()
            except ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
                if 'lines_json' in form.errors:
                    start_step = 2
                messages.error(
                    request,
                    'The sales order could not be saved. Please correct the errors and try again.',
                )
            else:
                messages.success(
                    request,
                    f'Sales order {"updated" if instance else "saved"} successfully. '
                    f'Internal ID {hed.order_id}, customer order {hed.cust_ord_id}.',
                )
                return redirect('transactions:sales_order')
        else:
            if 'lines_json' in form.errors:
                start_step = 2
            messages.error(
                request,
                'The sales order could not be saved. Please correct the errors and try again.',
            )
    else:
        form = SalesOrderForm(instance=instance)
        if instance:
            form.initial = form.get_initial()
        else:
            form.initial = {**form.get_initial(), **(form.initial or {})}

    sales_order_page_data = {
        'startStep': start_step,
        'isEdit': bool(instance),
    }
    ctx = {
        'form': form,
        'recent': _sales_order_recent_queryset(),
        'edit_instance': instance,
        'start_step': start_step,
        'sales_order_ajax_urls': _sales_order_ajax_urls(),
        'sales_order_page_data': sales_order_page_data,
        'products': _sales_order_products_payload(),
    }
    return render(request, 'transactions/sales_order_form.html', ctx)


@login_required
def sales_order_delete_view(request, pk):
    if request.method == 'POST':
        hed = get_object_or_404(
            TrnSlsOrdHed.objects.select_related('financial_year'),
            pk=pk,
        )
        fy = hed.financial_year
        if fy is not None and (not fy.is_open or fy.is_closed):
            messages.error(
                request,
                f'Cannot delete sales order in a closed financial year ({fy.fy_display}).',
            )
            return redirect('transactions:sales_order')
    return delete_object(request, TrnSlsOrdHed, pk, 'sales_order', 'cust_ord_id')


@login_required
@require_GET
def sales_order_product_meta_ajax(request):
    try:
        pk = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid prod_id'}, status=400)
    try:
        product = MstProd.objects.select_related('prod_type').get(pk=pk)
    except MstProd.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)

    styles = list(
        MstPkgStyle.objects.filter(pkg_type_id=product.prod_type_id)
        .order_by('pkg_style_name')
        .values('pkg_style_id', 'pkg_style_name', 'pkg_style_value')
    )
    return JsonResponse({
        'prod_id': product.pk,
        'hsn_code': (product.hsn_code or '').strip(),
        'item_type_id': product.prod_type_id,
        'packing_styles': styles,
    })


@login_required
@require_GET
def sales_order_customer_products_ajax(request):
    """
    Return products linked to the selected customer via MstCustProd.
    This drives the product dropdown so only customer-approved products are selectable.
    """
    try:
        cust_id = int(request.GET.get('cust_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid cust_id'}, status=400)

    prod_ids = (
        MstCustProd.objects.filter(customer_id=cust_id)
        .values_list('product_id', flat=True)
        .distinct()
    )
    rows = list(
        MstProd.objects.filter(prod_id__in=prod_ids)
        .order_by('prod_name')
        .values('prod_id', 'prod_name')
    )
    return JsonResponse({'products': rows})


def _batch_alloc_ajax_urls():
    return {
        'orders': reverse('transactions:batch_allocation_orders_ajax'),
        'orderDetail': reverse('transactions:batch_allocation_order_detail_ajax'),
        'products': reverse('transactions:batch_allocation_products_ajax'),
        'previousBatches': reverse('transactions:batch_allocation_previous_batches_ajax'),
    }

@login_required
def batch_allocation_view(request):
    if request.method == 'POST':
        form = BatchAllocationForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except django_forms.ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
            else:
                messages.success(request, 'Batches generated successfully.')
                return redirect('transactions:batch_allocation')
    else:
        form = BatchAllocationForm()

    return render(
        request,
        'transactions/batch_allocation_form.html',
        {
            'form': form,
            'batch_alloc_ajax_urls': _batch_alloc_ajax_urls(),
        },
    )


@login_required
@require_GET
def batch_allocation_orders_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid cust_id'}, status=400)
    rows = list(
        TrnSlsOrdHed.objects.filter(customer_id=cust_id)
        .order_by('-order_id')
        .values('order_id', 'cust_ord_id', 'ord_rec_dt')[:250]
    )
    for r in rows:
        d = r.get('ord_rec_dt')
        r['ord_rec_dt'] = d.isoformat() if d else ''
    return JsonResponse({'orders': rows})


@login_required
@require_GET
def batch_allocation_order_detail_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        order_id = int(request.GET.get('order_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    try:
        o = TrnSlsOrdHed.objects.get(pk=order_id, customer_id=cust_id)
    except TrnSlsOrdHed.DoesNotExist:
        return JsonResponse({'error': 'Invalid order selection'}, status=404)
    return JsonResponse({
        'order_id': o.order_id,
        'cust_ord_id': o.cust_ord_id,
        'ord_rec_dt': o.ord_rec_dt.isoformat() if o.ord_rec_dt else '',
        'remarks': o.remarks or '',
    })


@login_required
@require_GET
def batch_allocation_products_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        order_id = int(request.GET.get('order_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    try:
        o = TrnSlsOrdHed.objects.get(pk=order_id, customer_id=cust_id)
    except TrnSlsOrdHed.DoesNotExist:
        return JsonResponse({'error': 'Invalid order selection'}, status=404)

    lines = (
        TrnSlsOrdDtl1.objects.filter(order=o, is_completed=False)
        .exclude(remaining_qty__lte=0)
        .select_related('product', 'packing_style')
        .order_by('dtl1_id')
    )
    out = []
    for ln in lines:
        cp = MstCustProd.objects.filter(customer_id=cust_id, product_id=ln.product_id).first()
        abbr = (cp.batch_abbr or '').strip().upper() if cp else None
        disp = list(
            TrnSlsOrdDtl2.objects.filter(order=o, product_id=ln.product_id)
            .order_by('disp_sche_dt')
            .values_list('disp_sche_dt', flat=True)[:12]
        )
        disp_s = [d.isoformat() for d in disp]
        out.append({
            'dtl1_id': ln.dtl1_id,
            'prod_id': ln.product_id,
            'prod_name': ln.product.prod_name,
            'packing_style': ln.packing_style.pkg_style_name if ln.packing_style else '',
            'rate': str(ln.rate),
            'remaining_qty_l': str(ln.remaining_qty),
            'remaining_qty_n': str(ln.remaining_qty * 100000),
            'export_type': ln.export_type,
            'batch_abbr': abbr,
            'abbr_ok': bool(abbr and len(abbr) == 3),
            'dispatch_dates': disp_s,
        })
    return JsonResponse({'lines': out})


@login_required
@require_GET
def batch_allocation_previous_batches_ajax(request):
    try:
        order_id = int(request.GET.get('order_id', ''))
        line_id = int(request.GET.get('line_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    rows = list(
        TrnBatchDtl.objects.filter(batch__order_id=order_id, batch__order_line_id=line_id)
        .select_related('batch')
        .order_by('-batch_no')
        .values(
            'batch_no',
            'mfg_dt',
            'exp_dt',
            'batch_qty_l',
            'batch_qty_n',
        )[:400]
    )
    for r in rows:
        r['batch_qty_l'] = str(r['batch_qty_l'])
        r['batch_qty_n'] = str(r['batch_qty_n'])
    return JsonResponse({'batches': rows})


LOGSHEET_SESSION_SECTION = 'logsheet_last_section_id'
LOGSHEET_SESSION_SHIFT = 'logsheet_last_shift'


def _logsheet_ajax_urls():
    return {
        'pendingBatches': reverse('transactions:logsheet_pending_batches_ajax'),
        'productMeta': reverse('transactions:logsheet_product_meta_ajax'),
        'listRows': reverse('transactions:logsheet_list_ajax'),
        'customerProducts': reverse('transactions:logsheet_customer_products_ajax'),
    }


@login_required
def log_sheet_view(request):
    if request.method == 'POST':
        form = LogSheetForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except django_forms.ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
            else:
                request.session[LOGSHEET_SESSION_SECTION] = form.cleaned_data['section'].pk
                request.session[LOGSHEET_SESSION_SHIFT] = form.cleaned_data['shift']
                messages.success(request, 'Log sheet saved successfully.')
                return redirect('transactions:log_sheet')
    else:
        initial = {'gran_dt': timezone.localdate()}
        sid = request.session.get(LOGSHEET_SESSION_SECTION)
        sh = request.session.get(LOGSHEET_SESSION_SHIFT)
        if sid:
            initial['section'] = sid
        if sh in (LOGSHEET_SHIFT_DAY, LOGSHEET_SHIFT_NIGHT):
            initial['shift'] = sh
        form = LogSheetForm(initial=initial)

    end_d = timezone.localdate()
    start_d = end_d - timedelta(days=30)
    return render(
        request,
        'transactions/log_sheet_form.html',
        {
            'form': form,
            'logsheet_ajax_urls': _logsheet_ajax_urls(),
            'grid_defaults': {'start': start_d.isoformat(), 'end': end_d.isoformat()},
        },
    )


@login_required
@require_GET
def logsheet_customer_products_ajax(request):
    """
    Products that have at least one pending batch line for this customer
    (same scope as logsheet_pending_batches_ajax). Log sheet UI only lists
    actionable customer + product pairs.
    """
    try:
        cust_id = int(request.GET.get('cust_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid cust_id'}, status=400)

    prod_ids = (
        TrnBatchDtl.objects.filter(batch__customer_id=cust_id, log_sheet_flg='N')
        .values_list('batch__product_id', flat=True)
        .distinct()
    )
    rows = list(
        MstProd.objects.filter(prod_id__in=prod_ids)
        .order_by('prod_name')
        .values('prod_id', 'prod_name')
    )
    return JsonResponse({'products': rows})


@login_required
@require_GET
def logsheet_pending_batches_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        prod_id = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid customer or product'}, status=400)

    out = []
    for ln in (
        TrnBatchDtl.objects.filter(
            batch__customer_id=cust_id,
            batch__product_id=prod_id,
            log_sheet_flg='N',
        )
        .select_related(
            'batch',
            'batch__order',
            'batch__product',
            'batch__product__first_color',
            'batch__product__second_color',
        )
        .prefetch_related('log_sheets')
        .order_by('-dtl_id')[:500]
    ):
        o = ln.batch.order
        p = ln.batch.product
        layer = p.tablet_layer or MstProd.LAYER_SINGLE
        logged_slots = sorted(
            {s.layer_slot for s in ln.log_sheets.all() if s.layer_slot in ('S', '1', '2')}
        )
        n1, n2, l1, l2 = logsheet_split_batch_qty(ln.batch_qty_n, ln.batch_qty_l)
        c1 = p.first_color.color_name if p.first_color else ''
        c2 = p.second_color.color_name if p.second_color else ''
        out.append({
            'dtl_id': ln.dtl_id,
            'batch_no': ln.batch_no,
            'mfg_dt': ln.mfg_dt,
            'exp_dt': ln.exp_dt,
            'batch_qty_l': str(ln.batch_qty_l),
            'batch_qty_n': str(ln.batch_qty_n),
            'tablet_layer': layer,
            'first_color': c1,
            'second_color': c2,
            'logged_slots': logged_slots,
            'split_qty_n_first': n1,
            'split_qty_n_second': n2,
            'split_qty_l_first': str(l1),
            'split_qty_l_second': str(l2),
            'cust_ord_id': o.cust_ord_id if o else '',
            'ord_rec_dt': o.ord_rec_dt.isoformat() if o and o.ord_rec_dt else '',
        })
    return JsonResponse({'batches': out})


@login_required
@require_GET
def logsheet_product_meta_ajax(request):
    try:
        prod_id = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid prod_id'}, status=400)
    try:
        p = MstProd.objects.select_related('first_color', 'second_color').get(pk=prod_id)
    except MstProd.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)

    layer = p.tablet_layer or MstProd.LAYER_SINGLE
    c1 = p.first_color.color_name if p.first_color else ''
    c2 = p.second_color.color_name if p.second_color else ''
    if layer == MstProd.LAYER_DOUBLE:
        colour_display = ' / '.join(x for x in (c1, c2) if x) or '—'
    else:
        colour_display = c1 or '—'

    return JsonResponse({
        'prod_id': p.pk,
        'tablet_layer': layer,
        'colour_display': colour_display,
        'first_color': c1,
        'second_color': c2,
    })


@login_required
@require_GET
def logsheet_list_ajax(request):
    start_raw = (request.GET.get('start') or '').strip()
    end_raw = (request.GET.get('end') or '').strip()
    start_d = parse_date(start_raw)
    end_d = parse_date(end_raw)
    if not start_d or not end_d:
        return JsonResponse({'error': 'Start and end dates are required (YYYY-MM-DD).'}, status=400)
    if end_d < start_d:
        return JsonResponse({'error': 'End date must be on or after start date.'}, status=400)
    if (end_d - start_d).days > 90:
        return JsonResponse({'error': 'Date range must not exceed 90 days.'}, status=400)

    qs = (
        TrnLogSheet.objects.filter(gran_dt__range=(start_d, end_d))
        .select_related('section', 'product', 'batch_line', 'customer')
        .order_by('-gran_dt', '-logsheet_id')[:400]
    )
    rows = []
    for ls in qs:
        b = ls.batch_line
        slot = ls.layer_slot
        if slot == LOGSHEET_LAYER_SLOT_FIRST:
            slot_lbl = '1st colour'
        elif slot == LOGSHEET_LAYER_SLOT_SECOND:
            slot_lbl = '2nd colour'
        else:
            slot_lbl = '—'
        if slot in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
            n1, n2, l1, l2 = logsheet_split_batch_qty(b.batch_qty_n, b.batch_qty_l)
            if slot == LOGSHEET_LAYER_SLOT_FIRST:
                batch_summary = f'{b.batch_no} (L {l1} / Nos {n1})'
            else:
                batch_summary = f'{b.batch_no} (L {l2} / Nos {n2})'
        else:
            batch_summary = f'{b.batch_no} ({b.batch_qty_n})'
        rows.append({
            'logsheet_id': ls.logsheet_id,
            'section': ls.section.section_name,
            'gran_shift': f'{ls.gran_dt.strftime("%d-%m-%Y")}({ls.shift_id})',
            'product': ls.product.prod_name,
            'batch_summary': batch_summary,
            'layer_slot': slot_lbl,
            'mfg_exp': f'{b.mfg_dt} → {b.exp_dt}',
            'blend_dt': ls.blend_dt.strftime('%d-%m-%Y') if ls.blend_dt else '—',
            'customer': ls.customer.cust_name,
        })
    return JsonResponse({'rows': rows})


def _rm_dispensing_ajax_urls():
    return {
        'customerProducts': reverse('transactions:rm_dispensing_customer_products_ajax'),
        'batches': reverse('transactions:rm_dispensing_batches_ajax'),
        'specs': reverse('transactions:rm_dispensing_specs_ajax'),
        'bomItems': reverse('transactions:rm_dispensing_bom_items_ajax'),
        'listRows': reverse('transactions:rm_dispensing_list_ajax'),
        # Reuse existing product meta endpoint for layer/colour display.
        'productMeta': reverse('transactions:logsheet_product_meta_ajax'),
    }

def get_rm_dispensing_edit_instance(pk):
    if not pk:
        return None
    lines_qs = TrnlssDtl.objects.select_related('stage', 'item').order_by('dtl_id')
    return get_object_or_404(
        TrnlssHed.objects.select_related(
            'customer', 'product', 'batch_line', 'batch_line__batch_line', 'specification', 'machine',
        ).prefetch_related(
            Prefetch('lines', queryset=lines_qs),
        ),
        pk=pk,
    )


@login_required
def rm_dispensing_view(request):
    """
    RM dispensing entry.
    Uses JSON grid payload (lines_json) and server-side validation to maintain integrity.
    """
    edit_pk = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_rm_dispensing_edit_instance(edit_pk) if edit_pk else None

    if request.method == 'POST':
        form = RmDispensingForm(request.POST, instance=instance)
        if form.is_valid():
            try:
                hed = form.save()
            except ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
            else:
                messages.success(
                    request,
                    f'RM dispensing {"updated" if instance else "saved"} successfully. Internal ID {hed.dispensing_id}.',
                )
                return redirect('transactions:rm_dispensing')
    else:
        form = RmDispensingForm(instance=instance)
        form.initial = {**form.get_initial(), **(form.initial or {})}

    rm_edit_payload = None
    if instance:
        lines = []
        stage_ids = set()
        for ln in instance.lines.all():
            stage_ids.add(int(ln.stage_id))
            lines.append({
                'stage_id': int(ln.stage_id),
                'item_id': int(ln.item_id),
                'issue_qty': str(ln.issue_qty),
                'issue_add_qty': str(ln.issue_add_qty),
                'issue_date': ln.issue_date.isoformat() if ln.issue_date else '',
                'remarks': (ln.remarks or ''),
            })
        rm_edit_payload = {
            'dispensing_id': instance.dispensing_id,
            'selected_stage_ids': sorted(stage_ids),
            'lines': lines,
        }

    return render(
        request,
        'transactions/rm_dispensing_form.html',
        {
            'form': form,
            'edit_instance': instance,
            'rm_dispensing_ajax_urls': _rm_dispensing_ajax_urls(),
            'rm_edit_payload': rm_edit_payload,
        },
    )


@login_required
@require_GET
def rm_dispensing_customer_products_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid cust_id'}, status=400)

    prod_ids = (
        MstCustProd.objects.filter(customer_id=cust_id)
        .values_list('product_id', flat=True)
        .distinct()
    )
    rows = list(
        MstProd.objects.filter(prod_id__in=prod_ids)
        .order_by('prod_name')
        .values('prod_id', 'prod_name')
    )
    return JsonResponse({'products': rows})


@login_required
@require_GET
def rm_dispensing_batches_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        prod_id = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)

    out = []
    for ls in (
        TrnLogSheet.objects.filter(
            customer_id=cust_id,
            product_id=prod_id,
        )
        .select_related(
            'batch_line',
            'batch_line__batch',
            'batch_line__batch__order',
            'product',
            'product__first_color',
            'product__second_color',
        )
        .order_by('-gran_dt', '-logsheet_id')[:800]
    ):
        bl = ls.batch_line
        o = bl.batch.order if bl and bl.batch else None
        layer = (ls.product.tablet_layer if ls.product else None) or MstProd.LAYER_SINGLE
        c1 = ls.product.first_color.color_name if ls.product and ls.product.first_color else ''
        c2 = ls.product.second_color.color_name if ls.product and ls.product.second_color else ''
        n1, n2, l1, l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l) if bl else (0, 0, 0, 0)
        if layer == MstProd.LAYER_DOUBLE and ls.layer_slot in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
            if ls.layer_slot == LOGSHEET_LAYER_SLOT_FIRST:
                qty_l = l1
                qty_n = n1
                slot_lbl = f'1st ({c1 or "First colour"})'
            else:
                qty_l = l2
                qty_n = n2
                slot_lbl = f'2nd ({c2 or "Second colour"})'
        else:
            qty_l = bl.batch_qty_l if bl else ''
            qty_n = bl.batch_qty_n if bl else ''
            slot_lbl = 'Single' if ls.layer_slot == LOGSHEET_LAYER_SLOT_SINGLE else (ls.layer_slot or '—')

        out.append({
            'logsheet_id': ls.logsheet_id,
            'batch_no': bl.batch_no if bl else '',
            'gran_dt': ls.gran_dt.isoformat() if ls.gran_dt else '',
            'layer_slot': ls.layer_slot,
            'slot_label': slot_lbl,
            'mfg_dt': bl.mfg_dt if bl else '',
            'exp_dt': bl.exp_dt if bl else '',
            'batch_qty_l': str(qty_l),
            'batch_qty_n': str(qty_n),
            'batch_size_display': _dpr_batch_size_display(qty_l, qty_n),
            'cust_ord_id': o.cust_ord_id if o else '',
            'ord_rec_dt': o.ord_rec_dt.isoformat() if o and o.ord_rec_dt else '',
        })
    return JsonResponse({'logsheets': out})


@login_required
@require_GET
def rm_dispensing_specs_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        prod_id = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)

    specs = list(
        MstBomRmHed.objects.filter(customer_id=cust_id, product_id=prod_id)
        .order_by('-spec_id')
        .values('spec_id', 'spec_name', 'batch_size')
    )
    for s in specs:
        s['batch_size'] = str(s.get('batch_size') or '')
    return JsonResponse({'specs': specs})


@login_required
@require_GET
def rm_dispensing_bom_items_ajax(request):
    try:
        spec_id = int(request.GET.get('spec_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid spec_id'}, status=400)

    cust_id_raw = (request.GET.get('cust_id') or '').strip()
    cust_id = None
    if cust_id_raw:
        try:
            cust_id = int(cust_id_raw)
        except ValueError:
            return JsonResponse({'error': 'Invalid cust_id'}, status=400)

    logsheet_id_raw = (request.GET.get('logsheet_id') or '').strip()
    logsheet = None
    try:
        logsheet_id = int(logsheet_id_raw) if logsheet_id_raw else None
    except ValueError:
        return JsonResponse({'error': 'Invalid logsheet_id'}, status=400)
    try:
        spec = MstBomRmHed.objects.get(pk=spec_id)
    except MstBomRmHed.DoesNotExist:
        return JsonResponse({'error': 'Specification not found'}, status=404)

    if not spec.batch_size or spec.batch_size <= 0:
        return JsonResponse({'error': 'Invalid BOM batch size on specification.'}, status=400)

    # Optional: compute standard dispensing qty per (stage,item) for selected logsheet + spec.
    batch_size_l = None
    if logsheet_id:
        try:
            logsheet = TrnLogSheet.objects.select_related('batch_line', 'product').get(pk=logsheet_id)
        except TrnLogSheet.DoesNotExist:
            return JsonResponse({'error': 'Log sheet not found'}, status=404)
        bl = logsheet.batch_line
        if bl:
            layer = getattr(getattr(logsheet, 'product', None), 'tablet_layer', None) or MstProd.LAYER_SINGLE
            if layer == MstProd.LAYER_DOUBLE and logsheet.layer_slot in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
                n1, n2, l1, l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l)
                batch_size_l = l1 if logsheet.layer_slot == LOGSHEET_LAYER_SLOT_FIRST else l2
            else:
                batch_size_l = bl.batch_qty_l

    rows = []
    q3 = Decimal('0.001')
    for r in (
        MstBomRmDtl.objects.filter(spec_id=spec_id)
        .select_related('stage', 'item', 'item__uom')
        .order_by('dtl_id')
    ):
        qty_per_lakh = (r.qty / spec.batch_size) if spec.batch_size else 0
        uom = r.item.uom.short_name if r.item and r.item.uom else ''
        std_qty = None
        if batch_size_l is not None:
            try:
                std_qty = (Decimal(str(qty_per_lakh)) * Decimal(str(batch_size_l))).quantize(q3, rounding=ROUND_HALF_UP)
            except Exception:
                std_qty = qty_per_lakh * batch_size_l
        avail_qty = None
        if cust_id and r.item_id:
            from inventory.services import inventory_available_item_qty

            avail_qty = inventory_available_item_qty(cust_id, r.item_id)
        rows.append({
            'stage_id': r.stage_id,
            'stage_name': r.stage.stage_name if r.stage else '',
            'item_id': r.item_id,
            'item_name': r.item.item_name if r.item else '',
            'qty': str(r.qty),
            'qty_per_lakh': str(qty_per_lakh),
            'uom': uom,
            'std_qty': (str(std_qty) if std_qty is not None else None),
            'available_qty': (str(avail_qty) if avail_qty is not None else None),
        })
    return JsonResponse({'items': rows})


@login_required
@require_GET
def rm_dispensing_list_ajax(request):
    # Optional date range. If omitted, return latest rows (capped).
    start_raw = (request.GET.get('start') or '').strip()
    end_raw = (request.GET.get('end') or '').strip()
    start_d = parse_date(start_raw) if start_raw else None
    end_d = parse_date(end_raw) if end_raw else None
    if (start_raw or end_raw) and (not start_d or not end_d):
        return JsonResponse({'error': 'Invalid start/end dates (YYYY-MM-DD).'}, status=400)
    if start_d and end_d:
        if end_d < start_d:
            return JsonResponse({'error': 'End date must be on or after start date.'}, status=400)
        if (end_d - start_d).days > 180:
            return JsonResponse({'error': 'Date range must not exceed 180 days.'}, status=400)

    base_qs = (
        TrnlssHed.objects.all()
        .select_related(
            'customer',
            'product',
            'batch_line',
            'batch_line__batch_line',
            'specification',
        )
        .order_by('-dispensing_dt', '-dispensing_id')
    )
    if start_d and end_d:
        base_qs = base_qs.filter(dispensing_dt__range=(start_d, end_d))

    cust_id = (request.GET.get('cust_id') or '').strip()
    prod_id = (request.GET.get('prod_id') or '').strip()
    logsheet_id = (request.GET.get('logsheet_id') or '').strip()
    try:
        if cust_id:
            base_qs = base_qs.filter(customer_id=int(cust_id))
        if prod_id:
            base_qs = base_qs.filter(product_id=int(prod_id))
        if logsheet_id:
            base_qs = base_qs.filter(batch_line_id=int(logsheet_id))
    except ValueError:
        return JsonResponse({'error': 'Invalid filters.'}, status=400)

    # Apply a hard cap AFTER filtering. Important: avoid MySQL "LIMIT in subquery"
    # by not reusing this limited queryset inside an __in filter.
    qs = base_qs[:600]
    hed_ids = list(qs.values_list('dispensing_id', flat=True))

    # Stage summary per dispensing header.
    stage_counts = {}
    if hed_ids:
        stage_counts = {
            int(r['dispensing_id']): int(r['stages'] or 0)
            for r in (
                TrnlssDtl.objects.filter(dispensing_id__in=hed_ids)
                .values('dispensing_id')
                .annotate(stages=models.Count('stage_id', distinct=True))
            )
        }

    rows = []
    for hed in qs:
        bl = hed.batch_line.batch_line if hed.batch_line else None
        batch_no = getattr(bl, 'batch_no', '') if bl else ''
        slot = hed.batch_line.layer_slot if hed.batch_line else ''
        # Match label logic from rm_dispensing_batches_ajax.
        slot_lbl = 'Single' if slot == LOGSHEET_LAYER_SLOT_SINGLE else (slot or '—')
        rows.append({
            'dispensing_id': hed.dispensing_id,
            'dispensing_dt': hed.dispensing_dt.isoformat() if hed.dispensing_dt else '',
            'customer': hed.customer.cust_name if hed.customer else '',
            'product': hed.product.prod_name if hed.product else '',
            'batch_no': batch_no,
            'slot_label': slot_lbl,
            'spec': hed.specification.spec_name if hed.specification else '',
            'stage_count': int(stage_counts.get(hed.dispensing_id) or 0),
            'rm_complete': (hed.batch_line.rm_disp_flg if hed.batch_line else 'N'),
        })

    return JsonResponse({'rows': rows})


# ── Daily Production Report (DPR) ───────────────────────────────────────────

DPR_SESSION_SECTION = 'dpr_last_section_id'
DPR_SESSION_SHIFT = 'dpr_last_shift'


def _dpr_ajax_urls():
    return {
        'machines': reverse('transactions:dpr_machines_ajax'),
        'operators': reverse('transactions:dpr_operators_ajax'),
        'customerProducts': reverse('transactions:dpr_customer_products_ajax'),
        'logsheets': reverse('transactions:dpr_logsheets_ajax'),
        'specs': reverse('transactions:dpr_specs_ajax'),
        'sectionStatus': reverse('transactions:dpr_section_status_ajax'),
        'listRows': reverse('transactions:dpr_list_ajax'),
        'productMeta': reverse('transactions:logsheet_product_meta_ajax'),
    }


def _dpr_multi_batch_section_ids():
    return [s.section_id for s in MstSection.objects.all() if dpr_is_multi_batch_section(s)]


def get_dpr_edit_instance(pk):
    if not pk:
        return None
    try:
        pk_int = int(pk)
    except (TypeError, ValueError):
        return None
    return get_object_or_404(
        TrnDpr.objects.select_related(
            'section',
            'machine',
            'customer',
            'product',
            'batch_line',
            'log_sheet',
            'specification',
            'operator1',
            'operator2',
        ).prefetch_related(
            Prefetch(
                'input_batches',
                queryset=TrnDprInputBatch.objects.select_related(
                    'log_sheet',
                    'log_sheet__batch_line',
                    'log_sheet__product',
                    'log_sheet__product__first_color',
                    'log_sheet__product__second_color',
                ),
            ),
        ),
        pk=pk_int,
    )


def _dpr_edit_payload(instance):
    if not instance:
        return None
    payload = {
        'trn_dpr_id': instance.pk,
        'machine_working': instance.machine_working,
        'cust_id': instance.customer_id,
        'prod_id': instance.product_id,
        'batch_dtl_id': instance.batch_line_id,
        'log_sheet_id': instance.log_sheet_id,
        'spec_id': instance.specification_id,
    }
    if instance.machine_working == DPR_MACHINE_WORKING:
        if instance.operator1_id:
            payload['operator1_id'] = instance.operator1_id
        if instance.operator2_id:
            payload['operator2_id'] = instance.operator2_id
    if (
        instance.machine_working == DPR_MACHINE_WORKING
        and not instance.batch_line_id
        and instance.section_id
        and dpr_is_multi_batch_section(instance.section)
    ):
        ids = list(instance.input_batches.values_list('log_sheet_id', flat=True).order_by('input_id'))
        if ids:
            payload['multi_batch'] = True
            payload['log_sheet_ids'] = ids
            if instance.batch_size_lakh is not None:
                payload['batch_size_lakh'] = str(instance.batch_size_lakh)
    return payload


@login_required
def dpr_view(request):
    edit_pk = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_dpr_edit_instance(edit_pk) if edit_pk else None

    if request.method == 'POST':
        form = DprForm(request.POST, instance=instance)
        if form.is_valid():
            try:
                form.save(user=request.user)
            except django_forms.ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
            else:
                request.session[DPR_SESSION_SECTION] = form.cleaned_data['section'].pk
                request.session[DPR_SESSION_SHIFT] = form.cleaned_data['shift']
                verb = 'updated' if instance else 'saved'
                messages.success(request, f'Daily production report {verb} successfully.')
                return redirect('transactions:dpr')
    else:
        if instance:
            form = DprForm(instance=instance)
        else:
            initial = {'trn_dpr_dt': timezone.localdate()}
            sid = request.session.get(DPR_SESSION_SECTION)
            sh = request.session.get(DPR_SESSION_SHIFT)
            if sid:
                try:
                    initial['section'] = int(sid)
                except (TypeError, ValueError):
                    pass
            if sh in ('Day', 'Night', 'General'):
                initial['shift'] = sh
            form = DprForm(initial=initial)

    end_d = timezone.localdate()
    start_d = end_d - timedelta(days=30)
    return render(
        request,
        'transactions/dpr.html',
        {
            'form': form,
            'edit_instance': instance,
            'dpr_edit_payload': _dpr_edit_payload(instance) or {},
            'dpr_ajax_urls': _dpr_ajax_urls(),
            'dpr_multi_batch_section_ids': _dpr_multi_batch_section_ids(),
            'grid_defaults': {'start': start_d.isoformat(), 'end': end_d.isoformat()},
        },
    )


@login_required
@require_GET
def dpr_machines_ajax(request):
    try:
        section_id = int(request.GET.get('section_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid section'}, status=400)
    rows = list(
        MstMachine.objects.filter(section_id=section_id)
        .order_by('machine_name')
        .values('machine_id', 'machine_name')
    )
    return JsonResponse({'machines': rows})


@login_required
@require_GET
def dpr_operators_ajax(request):
    try:
        section_id = int(request.GET.get('section_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid section'}, status=400)
    out = []
    for r in (
        MstOperator.objects.filter(section_links__section_id=section_id)
        .distinct()
        .order_by('opt_name')
        .values('opt_id', 'opt_name', 'designation')
    ):
        label = r['opt_name']
        des = (r['designation'] or '').strip()
        if des:
            label = f"{label} — {des}"
        out.append({'opt_id': r['opt_id'], 'opt_name': r['opt_name'], 'label': label})
    return JsonResponse({'operators': out})


@login_required
@require_GET
def dpr_customer_products_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid cust_id'}, status=400)
    prod_ids = (
        TrnSlsOrdDtl1.objects.filter(order__customer_id=cust_id)
        .values_list('product_id', flat=True)
        .distinct()
    )
    rows = list(
        MstProd.objects.filter(prod_id__in=prod_ids).order_by('prod_name').values('prod_id', 'prod_name')
    )
    return JsonResponse({'products': rows})


def _dpr_batch_size_display(qty_l, qty_n) -> str:
    """Human-readable batch size: ``1.000 L / 100000 nos`` (lac to 3 decimals, nos as integer)."""
    l_part = ''
    n_part = ''
    if qty_l not in (None, ''):
        try:
            d = qty_l if isinstance(qty_l, Decimal) else Decimal(str(qty_l))
            l_part = f'{d:.3f} L'
        except (InvalidOperation, TypeError, ValueError, ArithmeticError):
            l_part = f'{qty_l} L'
    if qty_n not in (None, ''):
        try:
            d = qty_n if isinstance(qty_n, Decimal) else Decimal(str(qty_n))
            n_part = f'{int(d)} nos'
        except (InvalidOperation, TypeError, ValueError, ArithmeticError):
            n_part = f'{qty_n} nos'
    if l_part and n_part:
        return f'{l_part} / {n_part}'
    return l_part or n_part or ''


def _dpr_logsheet_batch_slot_caption(ls: TrnLogSheet) -> str:
    """Batch no. + colour slot label (same convention as the single-batch DPR dropdown)."""
    bl = ls.batch_line
    if not bl:
        return ''
    prod = ls.product
    layer = (prod.tablet_layer if prod else None) or MstProd.LAYER_SINGLE
    c1 = prod.first_color.color_name if prod and prod.first_color else ''
    c2 = prod.second_color.color_name if prod and prod.second_color else ''
    _n1, _n2, _l1, _l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l)
    if layer == MstProd.LAYER_DOUBLE and ls.layer_slot in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
        if ls.layer_slot == LOGSHEET_LAYER_SLOT_FIRST:
            slot_lbl = f'1st ({c1 or "First colour"})'
        else:
            slot_lbl = f'2nd ({c2 or "Second colour"})'
    else:
        slot_lbl = 'Single' if ls.layer_slot == LOGSHEET_LAYER_SLOT_SINGLE else (ls.layer_slot or '—')
    bn = bl.batch_no or ''
    s = (slot_lbl or '').strip()
    if s and s != 'Single':
        return f'{bn} — {slot_lbl}'
    return bn


@login_required
@require_GET
def dpr_logsheets_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        prod_id = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)

    out = []
    for ls in (
        TrnLogSheet.objects.filter(customer_id=cust_id, product_id=prod_id)
        .select_related(
            'batch_line',
            'batch_line__batch',
            'batch_line__batch__order',
            'product',
            'product__first_color',
            'product__second_color',
        )
        .order_by('-gran_dt', '-logsheet_id')[:800]
    ):
        bl = ls.batch_line
        o = bl.batch.order if bl and bl.batch else None
        layer = (ls.product.tablet_layer if ls.product else None) or MstProd.LAYER_SINGLE
        c1 = ls.product.first_color.color_name if ls.product and ls.product.first_color else ''
        c2 = ls.product.second_color.color_name if ls.product and ls.product.second_color else ''
        n1, n2, l1, l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l) if bl else (0, 0, 0, 0)
        if layer == MstProd.LAYER_DOUBLE and ls.layer_slot in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
            if ls.layer_slot == LOGSHEET_LAYER_SLOT_FIRST:
                qty_l, qty_n, slot_lbl = l1, n1, f'1st ({c1 or "First colour"})'
            else:
                qty_l, qty_n, slot_lbl = l2, n2, f'2nd ({c2 or "Second colour"})'
        else:
            qty_l = bl.batch_qty_l if bl else ''
            qty_n = bl.batch_qty_n if bl else ''
            slot_lbl = 'Single' if ls.layer_slot == LOGSHEET_LAYER_SLOT_SINGLE else (ls.layer_slot or '—')

        out.append({
            'logsheet_id': ls.logsheet_id,
            'batch_dtl_id': bl.dtl_id if bl else None,
            'batch_no': bl.batch_no if bl else '',
            'gran_dt': ls.gran_dt.isoformat() if ls.gran_dt else '',
            'layer_slot': ls.layer_slot,
            'slot_label': slot_lbl,
            'mfg_dt': bl.mfg_dt if bl else '',
            'exp_dt': bl.exp_dt if bl else '',
            'batch_qty_l': str(qty_l),
            'batch_qty_n': str(qty_n),
            'batch_size_display': _dpr_batch_size_display(qty_l, qty_n),
            'cust_ord_id': o.cust_ord_id if o else '',
            'ord_rec_dt': o.ord_rec_dt.isoformat() if o and o.ord_rec_dt else '',
        })
    return JsonResponse({'logsheets': out})


@login_required
@require_GET
def dpr_specs_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        prod_id = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    specs = list(
        MstBomRmHed.objects.filter(customer_id=cust_id, product_id=prod_id)
        .order_by('-spec_id')
        .values('spec_id', 'spec_name', 'batch_size')
    )
    for s in specs:
        s['batch_size'] = str(s.get('batch_size') or '')
    return JsonResponse({'specs': specs})


@login_required
@require_GET
def dpr_section_status_ajax(request):
    try:
        dtl_id = int(request.GET.get('batch_dtl_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid batch'}, status=400)
    if not dtl_id:
        return JsonResponse({'sections': []})

    sums = {
        int(r['section_id']): int(r['qty'] or 0)
        for r in (
            TrnDpr.objects.filter(batch_line_id=dtl_id, machine_working=DPR_MACHINE_WORKING)
            .values('section_id')
            .annotate(qty=Sum('qty_nos'))
        )
    }
    sections = list(MstSection.objects.all().order_by('section_name'))
    out = [{'section': s.section_name, 'qty_nos': sums.get(s.section_id, 0)} for s in sections]
    return JsonResponse({'sections': out})


@login_required
@require_GET
def dpr_list_ajax(request):
    start_raw = (request.GET.get('start') or '').strip()
    end_raw = (request.GET.get('end') or '').strip()
    start_d = parse_date(start_raw)
    end_d = parse_date(end_raw)
    if not start_d or not end_d:
        return JsonResponse({'error': 'Start and end dates are required (YYYY-MM-DD).'}, status=400)
    if end_d < start_d:
        return JsonResponse({'error': 'End date must be on or after start date.'}, status=400)
    if (end_d - start_d).days > 30:
        return JsonResponse({'error': 'Date range must not exceed 30 days.'}, status=400)

    qs = (
        TrnDpr.objects.filter(trn_dpr_dt__range=(start_d, end_d))
        .select_related(
            'section',
            'machine',
            'customer',
            'product',
            'batch_line',
            'log_sheet',
        )
        .prefetch_related(
            Prefetch(
                'input_batches',
                queryset=TrnDprInputBatch.objects.select_related(
                    'log_sheet',
                    'log_sheet__batch_line',
                    'log_sheet__product',
                    'log_sheet__product__first_color',
                    'log_sheet__product__second_color',
                ),
            ),
        )
        .order_by('-trn_dpr_dt', '-trn_dpr_id')[:500]
    )
    rows = []
    for r in qs:
        if r.batch_line_id:
            batch_no = r.batch_line.batch_no
            qty_cell = r.qty_nos
        else:
            parts = [
                _dpr_logsheet_batch_slot_caption(ib.log_sheet)
                for ib in sorted(r.input_batches.all(), key=lambda x: x.input_id)
                if ib.log_sheet_id
            ]
            batch_no = ' / '.join(p for p in parts if p) if parts else '—'
            qty_cell = r.qty_nos
        rows.append({
            'trn_dpr_id': r.trn_dpr_id,
            'trn_dpr_dt': r.trn_dpr_dt.strftime('%d-%m-%Y') if r.trn_dpr_dt else '',
            'section': r.section.section_name if r.section else '',
            'machine': r.machine.machine_name if r.machine else '',
            'shift': r.shift_id,
            'working': r.machine_working,
            'customer': r.customer.cust_name if r.customer else '—',
            'product': r.product.prod_name if r.product else '—',
            'batch_no': batch_no,
            'qty_nos': qty_cell,
            'total_time': r.total_time or '—',
        })
    return JsonResponse({'rows': rows})


def _pkg_cont_ajax_urls():
    return {
        'products': reverse('transactions:pkg_cont_products_ajax'),
        'logsheets': reverse('transactions:dpr_logsheets_ajax'),
        'styles': reverse('transactions:pkg_cont_styles_ajax'),
        'listRows': reverse('transactions:pkg_cont_list_ajax'),
    }


def get_pkg_cont_edit_instance(pk):
    if not pk:
        return None
    return get_object_or_404(
        TrnPkgCont.objects.select_related(
            'contractor',
            'log_sheet',
            'log_sheet__customer',
            'log_sheet__product',
            'log_sheet__batch_line',
            'pkg_style',
        ),
        pk=pk,
    )


@login_required
def pkg_cont_view(request):
    """Daily packing (contractors) — single-row entry with log sheet batch context."""
    edit_pk = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_pkg_cont_edit_instance(edit_pk) if edit_pk else None

    if request.method == 'POST':
        form = PkgContForm(request.POST, instance=instance)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
            else:
                messages.success(
                    request,
                    f'Daily packing (contractor) {"updated" if instance else "saved"} successfully.',
                )
                return redirect('transactions:pkg_cont')
    else:
        form = PkgContForm(instance=instance)
        form.initial = {**form.get_initial(), **(form.initial or {})}

    today = timezone.localdate()
    if instance and instance.pkgcont_date:
        pd = instance.pkgcont_date
        if pd > today:
            end_d = today
            start_d = end_d - timedelta(days=30)
        else:
            # 30-day window that includes the edited row (for list + Show data)
            end_d = min(today, pd + timedelta(days=14))
            start_d = end_d - timedelta(days=29)
            if pd < start_d:
                start_d = pd
                end_d = min(today, start_d + timedelta(days=29))
            if (end_d - start_d).days > 30:
                start_d = end_d - timedelta(days=30)
    else:
        end_d = today
        start_d = end_d - timedelta(days=30)
    return render(
        request,
        'transactions/pkg_cont_form.html',
        {
            'form': form,
            'edit_instance': instance,
            'pkg_cont_ajax_urls': _pkg_cont_ajax_urls(),
            'grid_defaults': {'start': start_d.isoformat(), 'end': end_d.isoformat()},
        },
    )


@login_required
def pkg_cont_delete_view(request, pk):
    return delete_object(request, TrnPkgCont, pk, 'transactions:pkg_cont', 'pkgcont_id')


@login_required
@require_GET
def pkg_cont_products_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid cust_id'}, status=400)
    prod_ids = (
        TrnLogSheet.objects.filter(customer_id=cust_id)
        .values_list('product_id', flat=True)
        .distinct()
    )
    rows = list(
        MstProd.objects.filter(prod_id__in=prod_ids).order_by('prod_name').values('prod_id', 'prod_name')
    )
    return JsonResponse({'products': rows})


@login_required
@require_GET
def pkg_cont_styles_ajax(request):
    try:
        prod_id = int(request.GET.get('prod_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid prod_id'}, status=400)
    try:
        prod = MstProd.objects.only('prod_type_id').get(pk=prod_id)
    except MstProd.DoesNotExist:
        return JsonResponse({'styles': []})
    rows = list(
        MstPkgStyle.objects.filter(pkg_type_id=prod.prod_type_id)
        .order_by('pkg_style_name')
        .values('pkg_style_id', 'pkg_style_name')
    )
    return JsonResponse({'styles': rows})


@login_required
@require_GET
def pkg_cont_list_ajax(request):
    start_raw = (request.GET.get('start') or '').strip()
    end_raw = (request.GET.get('end') or '').strip()
    start_d = parse_date(start_raw)
    end_d = parse_date(end_raw)
    if not start_d or not end_d:
        end_d = timezone.localdate()
        start_d = end_d - timedelta(days=30)
    if end_d < start_d:
        return JsonResponse({'error': 'End date must be on or after start date.'}, status=400)
    if (end_d - start_d).days > 30:
        return JsonResponse({'error': 'Date range must not exceed 30 days.'}, status=400)

    try:
        cust_id = int(request.GET.get('cust_id', '')) if (request.GET.get('cust_id') or '').strip() else None
    except ValueError:
        cust_id = None
    try:
        prod_id = int(request.GET.get('prod_id', '')) if (request.GET.get('prod_id') or '').strip() else None
    except ValueError:
        prod_id = None

    qs = (
        TrnPkgCont.objects.filter(pkgcont_date__range=(start_d, end_d))
        .select_related(
            'contractor',
            'pkg_style',
            'log_sheet',
            'log_sheet__product',
            'log_sheet__batch_line',
            'log_sheet__product__first_color',
            'log_sheet__product__second_color',
        )
        .order_by('-pkgcont_date', '-pkgcont_id')[:500]
    )
    if cust_id:
        qs = qs.filter(log_sheet__customer_id=cust_id)
    if prod_id:
        qs = qs.filter(log_sheet__product_id=prod_id)

    rows = []
    for r in qs:
        ls = r.log_sheet
        batch_display = _dpr_logsheet_batch_slot_caption(ls) if ls else ''
        rows.append({
            'pkgcont_id': r.pkgcont_id,
            'pkgcont_dt': r.pkgcont_date.strftime('%d-%m-%Y') if r.pkgcont_date else '',
            'contractor': r.contractor.opt_name if r.contractor_id else '',
            'product': ls.product.prod_name if ls and ls.product_id else '',
            'batch': batch_display,
            'pkg_style': r.pkg_style.pkg_style_name if r.pkg_style_id else '',
            'no_of_girls': r.no_of_girls if r.no_of_girls is not None else '',
            'shipper_no': r.shipper_no,
            'qty_nos': str(r.qty_nos or 0),
            'qty_loose': str(r.qty_loose) if r.qty_loose is not None else '',
            'remarks': (r.remarks or '')[:200],
            'delete_url': reverse('transactions:pkg_cont_delete', args=[r.pkgcont_id]),
            'delete_name': str(r.pkgcont_id),
        })
    return JsonResponse({'rows': rows})


def get_sales_invoice_edit_instance(pk):
    if not pk:
        return None
    batch_qs = TrnSlsDtl2.objects.select_related('log_sheet', 'log_sheet__batch_line').order_by('dtl2_id')
    lines_qs = (
        TrnSlsDtl1.objects.select_related('product', 'packing_style', 'order_line')
        .prefetch_related(Prefetch('batch_lines', queryset=batch_qs))
        .order_by('dtl1_id')
    )
    return get_object_or_404(
        TrnSlsHed.objects.select_related(
            'customer', 'transporter', 'financial_year', 'created_by', 'updated_by',
        ).prefetch_related(Prefetch('lines', queryset=lines_qs)),
        pk=pk,
    )


def _sales_invoice_recent_queryset():
    return (
        TrnSlsHed.objects.select_related('customer')
        .order_by('-invoice_id')[:40]
    )


def _sales_invoice_ajax_urls():
    return {
        'nextNumbers': reverse('transactions:sales_invoice_next_numbers_ajax'),
        'fgBatches': reverse('transactions:sales_invoice_fg_batches_ajax'),
        'orders': reverse('transactions:sales_invoice_orders_ajax'),
        'orderDetail': reverse('transactions:sales_invoice_order_detail_ajax'),
        'orderProducts': reverse('transactions:sales_invoice_order_products_ajax'),
    }


def _sales_invoice_number_suggest_payload():
    fy = get_or_create_financial_year_for_date(timezone.localdate())
    wy = fy.fy_display if fy else ''
    return {
        'invoice_no': suggested_sales_invoice_no(wy),
        'working_year': wy,
        'invoice_seq': max_invoice_sequence_for_fy(wy) + 1,
    }


@login_required
def sales_invoice_view(request):
    edit_pk = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_sales_invoice_edit_instance(edit_pk) if edit_pk else None
    start_step = 1

    if request.method == 'POST':
        form = SalesInvoiceForm(request.POST, instance=instance, user=request.user)
        if form.is_valid():
            try:
                hed = form.save()
            except ValidationError as exc:
                if getattr(exc, 'error_dict', None):
                    for field, errs in exc.error_dict.items():
                        form.add_error(field, errs)
                else:
                    form.add_error(None, exc)
                if 'lines_json' in form.errors:
                    start_step = 2
                elif 'reference_order' in form.errors:
                    start_step = 1
                messages.error(
                    request,
                    'The sales invoice could not be saved. Please correct the errors and try again.',
                )
            else:
                messages.success(
                    request,
                    f'Sales invoice {"updated" if instance else "saved"} successfully. '
                    f'Internal ID {hed.invoice_id}, {hed.invoice_no}.',
                )
                return redirect('transactions:sales_invoice')
        else:
            if 'lines_json' in form.errors:
                start_step = 2
            elif 'reference_order' in form.errors:
                start_step = 1
            messages.error(
                request,
                'The sales invoice could not be saved. Please correct the errors and try again.',
            )
    else:
        form = SalesInvoiceForm(instance=instance, user=request.user)
        if instance:
            form.initial = form.get_initial()
        else:
            form.initial = {**form.get_initial(), **(form.initial or {})}

    sales_invoice_page_data = {
        'startStep': start_step,
        'isEdit': bool(instance),
        'editPk': instance.pk if instance else None,
        'numberSuggest': _sales_invoice_number_suggest_payload(),
    }
    ctx = {
        'form': form,
        'recent': _sales_invoice_recent_queryset(),
        'edit_instance': instance,
        'start_step': start_step,
        'sales_invoice_ajax_urls': _sales_invoice_ajax_urls(),
        'sales_invoice_page_data': sales_invoice_page_data,
    }
    return render(request, 'transactions/sales_invoice_form.html', ctx)


@login_required
def sales_invoice_delete_view(request, pk):
    if request.method != 'POST':
        return redirect('transactions:sales_invoice')
    hed = get_object_or_404(
        TrnSlsHed.objects.select_related('financial_year').prefetch_related(
            'lines__order_line',
        ),
        pk=pk,
    )
    fy = hed.financial_year
    if fy is not None and (not fy.is_open or fy.is_closed):
        messages.error(
            request,
            f'Cannot delete sales invoice in a closed financial year ({fy.fy_display}).',
        )
        return redirect('transactions:sales_invoice')
    name = hed.invoice_no
    try:
        with transaction.atomic():
            reverse_sales_invoice_from_inventory(hed)
            affected = {
                ol_id for ol_id in hed.lines.values_list('order_line_id', flat=True) if ol_id
            }
            hed.delete()
            for ol_id in affected:
                refresh_order_line_sale_completed(ol_id)
        messages.success(request, f'"{name}" deleted successfully.')
    except ProtectedError as e:
        blocking = ', '.join(sorted({rel.__class__.__name__ for rel in e.protected_objects}))
        messages.error(
            request,
            f'Cannot delete "{name}" — it is referenced by: {blocking}.',
        )
    return redirect('transactions:sales_invoice')


@login_required
@require_GET
def sales_invoice_next_numbers_ajax(request):
    raw = (request.GET.get('invoice_dt') or '').strip()
    d = parse_date(raw) if raw else None
    if not d:
        d = timezone.localdate()
    fy = get_or_create_financial_year_for_date(d)
    wy = fy.fy_display if fy else ''
    return JsonResponse({
        'working_year': wy,
        'invoice_seq': max_invoice_sequence_for_fy(wy) + 1,
        'invoice_no': suggested_sales_invoice_no(wy),
    })


@login_required
@require_GET
def sales_invoice_fg_batches_ajax(request):
    from .forms.sales_invoice import _batch_dtl_remaining_qty_l

    try:
        cust_id = int(request.GET.get('cust_id', ''))
        order_id = int(request.GET.get('order_id', ''))
        order_line_id = int(request.GET.get('order_line_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)

    exclude_inv = (request.GET.get('exclude_invoice_id') or '').strip()
    exclude_inv_id = int(exclude_inv) if exclude_inv.isdigit() else None

    try:
        TrnSlsOrdDtl1.objects.select_related('order').get(
            pk=order_line_id,
            order_id=order_id,
            order__customer_id=cust_id,
        )
    except TrnSlsOrdDtl1.DoesNotExist:
        return JsonResponse({'error': 'Invalid order line'}, status=404)

    batch_lines = (
        TrnBatchDtl.objects.filter(
            batch__order_id=order_id,
            batch__order_line_id=order_line_id,
            batch__customer_id=cust_id,
            log_sheet_flg='Y',
            log_sheets__isnull=False,
        )
        .select_related('batch')
        .prefetch_related('log_sheets')
        .distinct()
        .order_by('-batch_no')[:400]
    )
    rows = []
    for bl in batch_lines:
        ls_count = len(bl.log_sheets.all())
        if ls_count < 1:
            continue
        remain = _batch_dtl_remaining_qty_l(bl, exclude_invoice_id=exclude_inv_id)
        if remain <= 0:
            continue
        label = bl.batch_no
        if ls_count > 1:
            label = f'{bl.batch_no} ({ls_count} colour runs)'
        rows.append({
            'batch_dtl_id': bl.dtl_id,
            'batch_no': bl.batch_no,
            'label': label,
            'mfg': bl.mfg_dt or '',
            'exp': bl.exp_dt or '',
            'batch_qty': str(remain),
            'log_sheet_count': ls_count,
        })
    return JsonResponse({'batches': rows})


@login_required
@require_GET
def sales_invoice_order_detail_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        order_id = int(request.GET.get('order_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    try:
        o = TrnSlsOrdHed.objects.get(pk=order_id, customer_id=cust_id)
    except TrnSlsOrdHed.DoesNotExist:
        return JsonResponse({'error': 'Invalid order selection'}, status=404)
    return JsonResponse({
        'order_id': o.order_id,
        'cust_ord_id': o.cust_ord_id,
        'ord_rec_dt': o.ord_rec_dt.isoformat() if o.ord_rec_dt else '',
        'pkg_fwd_amt': str(o.pkg_fwd_amt or 0),
        'freight_amt': str(o.frieght_amt or 0),
        'oth_charges': str(o.oth_charges or 0),
    })


@login_required
@require_GET
def sales_invoice_order_products_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
        order_id = int(request.GET.get('order_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    try:
        TrnSlsOrdHed.objects.get(pk=order_id, customer_id=cust_id)
    except TrnSlsOrdHed.DoesNotExist:
        return JsonResponse({'error': 'Invalid order selection'}, status=404)

    lines = (
        TrnSlsOrdDtl1.objects.filter(order_id=order_id)
        .select_related('product', 'packing_style')
        .order_by('dtl1_id')
    )
    out = []
    for ln in lines:
        out.append({
            'order_line_id': ln.dtl1_id,
            'prod_id': ln.product_id,
            'prod_name': ln.product.prod_name,
            'hsn_code': (ln.hsn_no or '').strip(),
            'pkg_style_id': ln.packing_style_id,
            'pkg_style_name': ln.packing_style.pkg_style_name if ln.packing_style else '',
            'pkg_style_value': ln.packing_style.pkg_style_value if ln.packing_style else None,
            'rate': str(ln.rate),
            'export_type': ln.export_type or '',
            'gst_type': ln.gst_type,
            'gst_per': str(ln.gst_per),
            'is_sale_completed': bool(ln.is_sale_completed),
        })
    return JsonResponse({'lines': out})


@login_required
@require_GET
def sales_invoice_orders_ajax(request):
    try:
        cust_id = int(request.GET.get('cust_id', ''))
    except ValueError:
        return JsonResponse({'error': 'Invalid cust_id'}, status=400)
    rows = list(
        TrnSlsOrdHed.objects.filter(customer_id=cust_id)
        .order_by('-ord_rec_dt', '-order_id')[:200]
        .values('order_id', 'cust_ord_id', 'ord_rec_dt')
    )
    inc = (request.GET.get('include_order_id') or '').strip()
    if inc:
        try:
            oid = int(inc)
        except ValueError:
            oid = None
        if oid is not None and not any(r['order_id'] == oid for r in rows):
            extra = (
                TrnSlsOrdHed.objects.filter(customer_id=cust_id, pk=oid)
                .values('order_id', 'cust_ord_id', 'ord_rec_dt')[:1]
            )
            rows = list(extra) + rows
    return JsonResponse({'orders': rows})


