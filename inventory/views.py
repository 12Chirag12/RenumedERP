"""
Inventory views: ledger browse, stock adjustment, AJAX helpers.
"""

import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from masters.models import MstCust, MstCustProd, MstItem, MstItemType, MstProd, MstProdCat

from .lifecycle import build_inventory_lifecycle
from .models import InventoryStock, TrnStkAdjHed
from .services import save_stock_adjustment_document
from .stock_adjustment_validation import (
    parse_stock_adjustment_body,
    validate_stock_adjustment_payload,
)


def _int_or_none(val) -> int | None:
    if val is None or (isinstance(val, str) and not str(val).strip()):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _category_id_from_get(raw: str | None) -> str:
    if not raw:
        return ''
    s = str(raw).strip().upper()[:2]
    if len(s) < 1:
        return ''
    if not MstProdCat.objects.filter(pk=s).exists():
        return ''
    return s


@login_required
@require_GET
def inventory_stock_view(request):
    """Read-only browse of ``InventoryStock`` with GET filters and pagination."""
    customers = MstCust.objects.order_by('cust_name')
    categories = MstProdCat.objects.order_by('prod_cat_name')

    customer_id = _int_or_none(request.GET.get('customer'))
    if customer_id is not None and not MstCust.objects.filter(pk=customer_id).exists():
        customer_id = None

    category_id = _category_id_from_get(request.GET.get('category'))

    product_id = _int_or_none(request.GET.get('product'))
    item_id = _int_or_none(request.GET.get('item'))

    sku_kind = (request.GET.get('sku_kind') or 'all').strip().lower()
    if sku_kind not in ('all', 'product', 'item'):
        sku_kind = 'all'

    batch_q = (request.GET.get('batch') or '').strip()[:100]
    show_zero = request.GET.get('show_zero') == '1'

    stock_opts = InventoryStock.objects.all()
    if customer_id is not None:
        stock_opts = stock_opts.filter(customer_id=customer_id)

    pids = stock_opts.exclude(product__isnull=True).values_list('product_id', flat=True).distinct()
    products = MstProd.objects.filter(pk__in=pids).order_by('prod_name')
    iids = stock_opts.exclude(item__isnull=True).values_list('item_id', flat=True).distinct()
    items = MstItem.objects.filter(pk__in=iids).order_by('item_name')

    allowed_pids = set(products.values_list('pk', flat=True))
    if product_id is not None and product_id not in allowed_pids:
        product_id = None
    allowed_iids = set(items.values_list('pk', flat=True))
    if item_id is not None and item_id not in allowed_iids:
        item_id = None

    qs = InventoryStock.objects.select_related(
        'customer',
        'product',
        'product__uom',
        'item',
        'item__uom',
        'item_category',
        'opened_in_fy',
    ).order_by('customer__cust_name', 'product__prod_name', 'item__item_name', 'batch_no')

    if customer_id is not None:
        qs = qs.filter(customer_id=customer_id)
    if category_id:
        qs = qs.filter(item_category_id=category_id)
    if product_id is not None:
        qs = qs.filter(product_id=product_id)
    if item_id is not None:
        qs = qs.filter(item_id=item_id)
    if sku_kind == 'product':
        qs = qs.filter(product__isnull=False)
    elif sku_kind == 'item':
        qs = qs.filter(item__isnull=False)
    if batch_q:
        qs = qs.filter(batch_no__icontains=batch_q)
    if not show_zero:
        qs = qs.filter(Q(qty__gt=0) | Q(reserved_qty__gt=0))

    paginator = Paginator(qs, 50)
    page_num = _int_or_none(request.GET.get('page')) or 1
    page_obj = paginator.get_page(page_num)

    q = request.GET.copy()
    q.pop('page', None)
    filter_query = q.urlencode()

    total = paginator.count
    result_summary = f'Showing {len(page_obj.object_list)} row(s) on this page — {total} match(es) in total.'

    return render(
        request,
        'inventory/inventory_stock_view.html',
        {
            'customers': customers,
            'categories': categories,
            'products': products,
            'items': items,
            'page_obj': page_obj,
            'filter_query': filter_query,
            'result_summary': result_summary,
            'sel_customer_id': customer_id,
            'sel_category_id': category_id,
            'sel_product_id': product_id,
            'sel_item_id': item_id,
            'sel_sku_kind': sku_kind,
            'sel_batch': batch_q,
            'sel_show_zero': show_zero,
        },
    )


@login_required
@require_GET
def inventory_stock_lifecycle_ajax(request):
    """Batch-wise movement history for one inventory ledger row (JSON)."""
    inv_id = _int_or_none(request.GET.get('inv_id'))
    if inv_id is None:
        return JsonResponse({'error': 'inv_id is required.'}, status=400)

    row = get_object_or_404(
        InventoryStock.objects.select_related('customer', 'product', 'item'),
        pk=inv_id,
    )
    try:
        payload = build_inventory_lifecycle(
            customer_id=row.customer_id,
            product_id=row.product_id,
            item_id=row.item_id,
            batch_no=row.batch_no,
        )
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    payload['inv_id'] = row.inv_id
    return JsonResponse(payload)


def _stock_adj_document_dict(hed: TrnStkAdjHed) -> dict:
    lines = []
    for ln in hed.lines.prefetch_related('batches').select_related('product', 'item'):
        kind = 'P' if ln.product_id else 'I'
        mid = ln.product_id or ln.item_id
        label = ln.product.prod_name if kind == 'P' else ln.item.item_name
        batches = []
        for b in ln.batches.all():
            batches.append(
                {
                    'batch_no': b.batch_no,
                    'mfg_date': b.mfg_date.isoformat() if b.mfg_date else '',
                    'exp_date': b.exp_date.isoformat() if b.exp_date else '',
                    'batch_qty': str(b.batch_qty),
                }
            )
        lines.append(
            {
                'kind': kind,
                'master_id': mid,
                'label': label,
                'remarks': ln.line_remarks,
                'batches': batches,
            }
        )
    return {
        'stk_adj_id': hed.stk_adj_id,
        'customer_id': hed.customer_id,
        'stk_adj_dt': hed.stk_adj_dt.isoformat(),
        'stk_adj_type': hed.stk_adj_type,
        'item_type_id': hed.item_type_id,
        'remarks': hed.remarks or '',
        'lines': lines,
    }


@login_required
@require_GET
def stock_adjustment_masters_ajax(request):
    """Return product or item rows for the selected customer + item type."""
    try:
        customer_id = int(request.GET.get('customer_id') or 0)
    except (TypeError, ValueError):
        customer_id = 0
    try:
        item_type_id = int(request.GET.get('item_type_id') or 0)
    except (TypeError, ValueError):
        item_type_id = 0
    if customer_id <= 0 or item_type_id <= 0:
        return JsonResponse({'mode': '', 'rows': []})

    cust_prods = (
        MstCustProd.objects.filter(customer_id=customer_id, product__prod_type_id=item_type_id)
        .select_related('product')
        .order_by('product__prod_name')
    )
    if cust_prods.exists():
        rows = [{'id': cp.product_id, 'label': cp.product.prod_name} for cp in cust_prods]
        return JsonResponse({'mode': 'P', 'rows': rows})

    items = MstItem.objects.filter(item_type_id=item_type_id).order_by('item_name')
    rows = [{'id': it.item_id, 'label': it.item_name} for it in items]
    return JsonResponse({'mode': 'I', 'rows': rows})


@login_required
@require_GET
def stock_adjustment_sku_meta_ajax(request):
    """
    Mfg/exp field enablement from item master (Y/N flags). Products (FG) always allow dates.
    """
    try:
        customer_id = int(request.GET.get('customer_id') or 0)
    except (TypeError, ValueError):
        customer_id = 0
    try:
        master_id = int(request.GET.get('master_id') or 0)
    except (TypeError, ValueError):
        master_id = 0
    kind = (request.GET.get('kind') or '').strip().upper()
    if customer_id <= 0 or master_id <= 0 or kind not in ('P', 'I'):
        return JsonResponse({'maintain_batch': 'N', 'mfg_enabled': True, 'exp_enabled': True})
    if kind == 'P':
        if not MstCustProd.objects.filter(customer_id=customer_id, product_id=master_id).exists():
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse({'maintain_batch': 'Y', 'mfg_enabled': True, 'exp_enabled': True})
    it = MstItem.objects.filter(pk=master_id).first()
    if not it:
        return JsonResponse({'error': 'not_found'}, status=404)
    return JsonResponse(
        {
            'maintain_batch': it.maintain_batch or 'N',
            'mfg_enabled': it.mfg_date == 'Y',
            'exp_enabled': it.exp_date == 'Y',
        }
    )


@login_required
@require_GET
def stock_adjustment_inv_defaults_ajax(request):
    """Suggest mfg/exp from existing ledger row for this customer + SKU + batch (optional)."""
    try:
        customer_id = int(request.GET.get('customer_id') or 0)
    except (TypeError, ValueError):
        customer_id = 0
    try:
        master_id = int(request.GET.get('master_id') or 0)
    except (TypeError, ValueError):
        master_id = 0
    kind = (request.GET.get('kind') or '').strip().upper()
    batch_no = (request.GET.get('batch_no') or '').strip()[:100]
    if customer_id <= 0 or master_id <= 0 or kind not in ('P', 'I'):
        return JsonResponse({'mfg_date': '', 'exp_date': ''})

    flt: dict = {'customer_id': customer_id, 'batch_no': batch_no}
    if kind == 'P':
        flt['product_id'] = master_id
        flt['item_id'] = None
    else:
        flt['item_id'] = master_id
        flt['product_id'] = None
    row = InventoryStock.objects.filter(**flt, is_closed=False).first()
    if not row:
        return JsonResponse({'mfg_date': '', 'exp_date': ''})
    return JsonResponse(
        {
            'mfg_date': row.mfg_date.isoformat() if row.mfg_date else '',
            'exp_date': row.exp_date.isoformat() if row.exp_date else '',
        }
    )


@login_required
@require_http_methods(['GET', 'POST'])
def stock_adjustment_view(request):
    customers = MstCust.objects.order_by('cust_name')
    item_types = MstItemType.objects.select_related('item_category').order_by('item_type_name')

    try:
        edit_pk = int(request.GET.get('edit_pk') or request.POST.get('edit_pk') or 0)
    except (TypeError, ValueError):
        edit_pk = 0

    initial_doc = None
    if edit_pk:
        hed = get_object_or_404(TrnStkAdjHed, pk=edit_pk)
        initial_doc = _stock_adj_document_dict(hed)

    repost_doc = None

    if request.method == 'POST':
        raw = request.POST.get('stk_adj_document') or ''
        e1, body = parse_stock_adjustment_body(raw)
        if e1:
            for msg in e1:
                messages.error(request, msg)
            repost_doc = raw or None
        else:
            try:
                edit_pk_post = int(request.POST.get('edit_pk') or 0)
            except (TypeError, ValueError):
                edit_pk_post = 0
            e2, cleaned = validate_stock_adjustment_payload(body, edit_pk=edit_pk_post or None)
            if e2:
                for msg in e2[:25]:
                    messages.error(request, msg)
                if len(e2) > 25:
                    messages.error(request, 'Fix the errors above (additional messages omitted).')
                repost_doc = raw
            else:
                assert cleaned is not None
                try:
                    hed = save_stock_adjustment_document(
                        header_pk=cleaned['header_pk'],
                        customer_id=cleaned['customer_id'],
                        stk_adj_dt=cleaned['stk_adj_dt'],
                        stk_adj_type=cleaned['stk_adj_type'],
                        item_type_id=cleaned['item_type_id'],
                        remarks=cleaned['remarks'],
                        lines_payload=cleaned['lines'],
                    )
                except ValidationError as exc:
                    for msg in exc.messages:
                        messages.error(request, msg)
                    repost_doc = raw
                else:
                    messages.success(request, 'Stock adjustment saved.')
                    return redirect('inventory:stock_adjustment')

    display_initial = initial_doc
    if repost_doc:
        try:
            display_initial = json.loads(repost_doc)
        except json.JSONDecodeError:
            pass

    return render(
        request,
        'inventory/stock_adjustment.html',
        {
            'customers': customers,
            'item_types': item_types,
            'initial_doc': display_initial,
            'edit_pk': edit_pk or None,
            'today': date.today().isoformat(),
        },
    )
