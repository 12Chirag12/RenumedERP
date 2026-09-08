"""
Reconstruct batch-level inventory movement history from source transactions.

The ``InventoryStock`` ledger stores current balances only; this module replays
inward, opening/adjustment, DPR, RM dispensing, and sales-invoice postings using
the same rules as ``inventory.transaction_posting``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum
from django.urls import reverse

from transactions.constants import QTY_DECIMAL_PLACES
from transactions.models import (
    DPR_MACHINE_WORKING,
    TrnDpr,
    TrnInwDtl1,
    TrnInwHed,
    TrnSlsDtl2,
    TrnSlsHed,
    TrnlssDtl,
    TrnlssHed,
)

from .models import InventoryStock, TrnStkAdjDtl2, TrnStkAdjHed
from .transaction_posting import (
    REF_DOC_DPR,
    REF_DOC_INW,
    REF_DOC_RM_DISP,
    REF_DOC_SLS_INV,
    _dpr_posting_batch_key,
    _dpr_production_lac,
    _dpr_section_contributes_fg_inventory,
    _inward_item_inventory_postings,
    _rm_line_issue_total,
)
from .services import REF_DOC_TYPE_STK_ADJ

_QUANT = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)

# Sort order within the same calendar date.
_TYPE_ORDER = {
    'OPENING': 10,
    'INWARD': 20,
    'DPR': 30,
    'ADJUST': 40,
    'RM_DISPENSE': 50,
    'SALES_INV': 60,
}


def _q(d) -> Decimal:
    return Decimal(str(d or 0)).quantize(_QUANT, rounding=ROUND_HALF_UP)


def _norm_batch(batch_no: str | None) -> str:
    return (batch_no or '').strip()


@dataclass
class _RawEvent:
    trn_date: date
    type_key: str
    label: str
    qty_delta: Decimal
    doc_type: str
    doc_id: int
    doc_display: str
    detail: str = ''
    sort_tie: int = 0
    item_level_only: bool = False


def _doc_url(doc_type: str, doc_id: int) -> str | None:
    if not doc_id:
        return None
    routes = {
        REF_DOC_INW: ('transactions:inward', 'edit_pk'),
        REF_DOC_TYPE_STK_ADJ: ('inventory:stock_adjustment', 'edit_pk'),
        REF_DOC_RM_DISP: ('transactions:rm_dispensing', 'edit_pk'),
        REF_DOC_DPR: ('transactions:dpr', 'edit_pk'),
        REF_DOC_SLS_INV: ('transactions:sales_invoice', 'edit_pk'),
    }
    spec = routes.get(doc_type)
    if not spec:
        return None
    name, param = spec
    return f'{reverse(name)}?{param}={doc_id}'


def _collect_inward_events(*, customer_id: int, item_id: int, batch_no: str) -> list[_RawEvent]:
    events: list[_RawEvent] = []
    bn = _norm_batch(batch_no)
    d1_qs = TrnInwDtl1.objects.filter(
        inward__customer_id=customer_id,
        item_id=item_id,
    ).select_related('inward', 'item').order_by('inward__inward_dt', 'inward_id', 'dtl1_id')

    for d1 in d1_qs:
        hed = d1.inward
        for b, posted in _inward_item_inventory_postings(d1, hed):
            line_bn = _norm_batch(b.batch_no if b else '')
            if line_bn != bn:
                continue
            if posted <= 0:
                continue
            detail = f'Posted {_q(posted)} to inventory'
            if b is not None:
                recv = _q(b.batch_qty)
                if recv > posted:
                    detail = f'Posted {_q(posted)} (received {_q(recv)}, sample {_q(recv - posted)})'
            events.append(
                _RawEvent(
                    trn_date=hed.inward_dt,
                    type_key='INWARD',
                    label='Inward (GRN)',
                    qty_delta=posted,
                    doc_type=REF_DOC_INW,
                    doc_id=hed.pk,
                    doc_display=f'{hed.grn_no} / {hed.register_no}',
                    detail=detail,
                    sort_tie=d1.dtl1_id,
                )
            )
    return events


def _collect_stock_adj_events(
    *, customer_id: int, product_id: int | None, item_id: int | None, batch_no: str
) -> list[_RawEvent]:
    events: list[_RawEvent] = []
    bn = _norm_batch(batch_no)
    flt = {
        'line__header__customer_id': customer_id,
        'batch_no': bn,
    }
    if product_id:
        flt['line__product_id'] = product_id
        flt['line__item_id__isnull'] = True
    else:
        flt['line__item_id'] = item_id
        flt['line__product_id__isnull'] = True

    rows = (
        TrnStkAdjDtl2.objects.filter(**flt)
        .select_related('line__header')
        .order_by('line__header__stk_adj_dt', 'line__header_id', 'dtl2_id')
    )
    for b in rows:
        hed: TrnStkAdjHed = b.line.header
        qty = _q(b.batch_qty)
        if qty == 0:
            continue
        is_opening = hed.stk_adj_type == TrnStkAdjHed.TYPE_OPENING
        events.append(
            _RawEvent(
                trn_date=hed.stk_adj_dt,
                type_key='OPENING' if is_opening else 'ADJUST',
                label='Opening balance' if is_opening else 'Stock adjustment',
                qty_delta=qty,
                doc_type=REF_DOC_TYPE_STK_ADJ,
                doc_id=hed.pk,
                doc_display=f'#{hed.pk} ({hed.get_stk_adj_type_display()})',
                detail=f'Batch qty {_q(qty)}',
                sort_tie=b.dtl2_id,
            )
        )
    return events


def _collect_rm_dispensing_events(*, customer_id: int, item_id: int) -> list[_RawEvent]:
    """RM dispensing posts to item-level bucket (empty batch no.)."""
    events: list[_RawEvent] = []
    lines = (
        TrnlssDtl.objects.filter(
            dispensing__customer_id=customer_id,
            item_id=item_id,
        )
        .select_related('dispensing', 'stage')
        .order_by('issue_date', 'dispensing_id', 'dtl_id')
    )
    for ln in lines:
        tot = _rm_line_issue_total(ln)
        if tot <= 0:
            continue
        hed: TrnlssHed = ln.dispensing
        std = _q(ln.issue_qty)
        add = _q(ln.issue_add_qty)
        parts = []
        if std > 0:
            parts.append(f'standard {std}')
        if add > 0:
            parts.append(f'additional {add}')
        events.append(
            _RawEvent(
                trn_date=ln.issue_date,
                type_key='RM_DISPENSE',
                label='RM dispensing',
                qty_delta=-tot,
                doc_type=REF_DOC_RM_DISP,
                doc_id=hed.pk,
                doc_display=f'#{hed.dispensing_id}',
                detail='; '.join(parts) if parts else f'Total {tot}',
                sort_tie=ln.dtl_id,
                item_level_only=True,
            )
        )
    return events


def _collect_dpr_events(*, customer_id: int, product_id: int, batch_no: str) -> list[_RawEvent]:
    events: list[_RawEvent] = []
    bn = _norm_batch(batch_no)
    rows = (
        TrnDpr.objects.filter(
            customer_id=customer_id,
            product_id=product_id,
            machine_working=DPR_MACHINE_WORKING,
        )
        .select_related('section', 'batch_line')
        .order_by('trn_dpr_dt', 'trn_dpr_id')
    )
    for row in rows:
        if not _dpr_section_contributes_fg_inventory(getattr(row, 'section', None)):
            continue
        lac = _dpr_production_lac(row)
        lac = lac.quantize(_QUANT, rounding=ROUND_HALF_UP)
        if lac <= 0:
            continue
        row_bn, _, _ = _dpr_posting_batch_key(row)
        if _norm_batch(row_bn) != bn:
            continue
        sec = row.section.section_name if row.section else '—'
        events.append(
            _RawEvent(
                trn_date=row.trn_dpr_dt,
                type_key='DPR',
                label='DPR (FG production)',
                qty_delta=lac,
                doc_type=REF_DOC_DPR,
                doc_id=row.pk,
                doc_display=f'#{row.trn_dpr_id}',
                detail=f'Section: {sec}',
                sort_tie=row.trn_dpr_id,
            )
        )
    return events


def _collect_sales_invoice_events(*, customer_id: int, product_id: int, batch_no: str) -> list[_RawEvent]:
    events: list[_RawEvent] = []
    bn = _norm_batch(batch_no)
    rows = (
        TrnSlsDtl2.objects.filter(
            invoice_line__invoice__customer_id=customer_id,
            invoice_line__product_id=product_id,
            log_sheet__batch_line__batch_no=bn,
        )
        .select_related('invoice_line__invoice', 'log_sheet__batch_line')
        .order_by('invoice_line__invoice__invoice_dt', 'invoice_line__invoice_id', 'dtl2_id')
    )
    for d2 in rows:
        hed: TrnSlsHed = d2.invoice_line.invoice
        posted = _q(d2.batch_qty)
        if posted <= 0:
            continue
        events.append(
            _RawEvent(
                trn_date=hed.invoice_dt,
                type_key='SALES_INV',
                label='Sales invoice',
                qty_delta=-posted,
                doc_type=REF_DOC_SLS_INV,
                doc_id=hed.pk,
                doc_display=hed.invoice_no,
                detail=f'Batch dispatch {_q(posted)} (lac)',
                sort_tie=d2.dtl2_id,
            )
        )
    return events


def _ledger_episodes(*, customer_id: int, product_id: int | None, item_id: int | None, batch_no: str) -> list[dict]:
    flt = {'customer_id': customer_id, 'batch_no': _norm_batch(batch_no)}
    if product_id:
        flt['product_id'] = product_id
        flt['item_id'] = None
    else:
        flt['item_id'] = item_id
        flt['product_id'] = None
    rows = (
        InventoryStock.objects.filter(**flt)
        .select_related('opened_in_fy')
        .order_by('inv_id')
    )
    out = []
    for r in rows:
        out.append({
            'inv_id': r.inv_id,
            'qty': str(_q(r.qty)),
            'reserved_qty': str(_q(r.reserved_qty)),
            'is_closed': r.is_closed,
            'opened_fy': r.opened_in_fy.fy_display if r.opened_in_fy else '',
            'last_trn_date': r.last_trn_date.isoformat() if r.last_trn_date else '',
            'last_trn_type': r.last_trn_type or '',
        })
    return out


def build_inventory_lifecycle(
    *,
    customer_id: int,
    product_id: int | None,
    item_id: int | None,
    batch_no: str,
) -> dict:
    """
    Return chronological movements and running balance for one ledger bucket key.
    """
    if bool(product_id) == bool(item_id):
        raise ValueError('Exactly one of product_id or item_id is required.')

    bn = _norm_batch(batch_no)
    raw: list[_RawEvent] = []

    if item_id:
        raw.extend(_collect_inward_events(customer_id=customer_id, item_id=item_id, batch_no=bn))
        raw.extend(
            _collect_stock_adj_events(
                customer_id=customer_id, product_id=None, item_id=item_id, batch_no=bn
            )
        )
        if not bn:
            raw.extend(_collect_rm_dispensing_events(customer_id=customer_id, item_id=item_id))
    else:
        raw.extend(
            _collect_stock_adj_events(
                customer_id=customer_id, product_id=product_id, item_id=None, batch_no=bn
            )
        )
        raw.extend(
            _collect_dpr_events(customer_id=customer_id, product_id=product_id, batch_no=bn)
        )
        raw.extend(
            _collect_sales_invoice_events(
                customer_id=customer_id, product_id=product_id, batch_no=bn
            )
        )

    raw.sort(
        key=lambda e: (
            e.trn_date,
            _TYPE_ORDER.get(e.type_key, 99),
            e.sort_tie,
            e.doc_id,
        )
    )

    balance = Decimal('0')
    batch_events: list[dict] = []
    item_level_events: list[dict] = []

    for e in raw:
        if e.item_level_only and bn:
            item_level_events.append(_serialize_event(e, None))
            continue
        balance = _q(balance + e.qty_delta)
        batch_events.append(_serialize_event(e, balance))

    stock_row = InventoryStock.objects.filter(
        customer_id=customer_id,
        batch_no=bn,
        product_id=product_id,
        item_id=item_id,
    ).select_related('customer', 'product', 'product__uom', 'item', 'item__uom').order_by('-inv_id').first()

    sku_name = ''
    uom = ''
    if stock_row:
        if stock_row.product_id:
            sku_name = stock_row.product.prod_name
            uom = stock_row.product.uom.short_name if stock_row.product.uom else ''
        else:
            sku_name = stock_row.item.item_name
            uom = stock_row.item.uom.short_name if stock_row.item.uom else ''
        customer_name = stock_row.customer.cust_name
    else:
        from masters.models import MstCust, MstItem, MstProd

        customer_name = MstCust.objects.filter(pk=customer_id).values_list('cust_name', flat=True).first() or ''
        if product_id:
            p = MstProd.objects.select_related('uom').filter(pk=product_id).first()
            if p:
                sku_name = p.prod_name
                uom = p.uom.short_name if p.uom else ''
        elif item_id:
            it = MstItem.objects.select_related('uom').filter(pk=item_id).first()
            if it:
                sku_name = it.item_name
                uom = it.uom.short_name if it.uom else ''

    open_sum = InventoryStock.objects.filter(
        customer_id=customer_id,
        batch_no=bn,
        product_id=product_id,
        item_id=item_id,
        is_closed=False,
    ).aggregate(total=Sum('qty'))['total']
    ledger_qty = _q(open_sum)

    return {
        'customer_name': customer_name,
        'sku_name': sku_name,
        'sku_kind': 'product' if product_id else 'item',
        'batch_no': bn or '—',
        'uom': uom,
        'ledger_qty': str(ledger_qty),
        'computed_balance': str(balance),
        'balance_matches_ledger': balance == ledger_qty,
        'events': batch_events,
        'item_level_events': item_level_events,
        'ledger_episodes': _ledger_episodes(
            customer_id=customer_id,
            product_id=product_id,
            item_id=item_id,
            batch_no=bn,
        ),
        'note': (
            'RM dispensing is recorded at item level (no batch). Movements appear under '
            '“Item-level issues” when viewing a specific batch.'
            if item_id and bn and item_level_events
            else ''
        ),
    }


def _serialize_event(e: _RawEvent, balance_after: Decimal | None) -> dict:
    return {
        'trn_date': e.trn_date.isoformat(),
        'type_key': e.type_key,
        'label': e.label,
        'qty_delta': str(_q(e.qty_delta)),
        'qty_delta_display': f'{_q(e.qty_delta):+f}',
        'balance_after': str(balance_after) if balance_after is not None else '',
        'doc_type': e.doc_type,
        'doc_id': e.doc_id,
        'doc_display': e.doc_display,
        'detail': e.detail,
        'doc_url': _doc_url(e.doc_type, e.doc_id),
    }
