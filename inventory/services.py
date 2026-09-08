"""
Central inventory ledger updates (InventoryStock).

Other modules (inward, dispensing, sales invoices, …) should call into this layer so
balances stay consistent without scanning all transaction tables at read time.

Document-level post/reverse helpers for Trn* tables live in
``inventory.transaction_posting`` (called from ``transactions.forms`` / views).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from transactions.constants import QTY_DECIMAL_PLACES
from transactions.utils import get_or_create_financial_year_for_date

if TYPE_CHECKING:
    from .models import TrnStkAdjHed

REF_DOC_TYPE_STK_ADJ = 'STK_ADJ'
LAST_TRN_OPENING = 'OPENING'
LAST_TRN_ADJUST = 'ADJUST'

_QUANT = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)


def _q(d) -> Decimal:
    return Decimal(str(d or 0)).quantize(_QUANT, rounding=ROUND_HALF_UP)


def inventory_available_item_qty(customer_id: int, item_id: int) -> Decimal:
    """Sum open ``InventoryStock`` qty for a customer item (all batch buckets)."""
    from django.db.models import Sum

    from .models import InventoryStock

    t = (
        InventoryStock.objects.filter(
            customer_id=customer_id,
            item_id=item_id,
            product_id__isnull=True,
            is_closed=False,
        ).aggregate(s=Sum('qty'))['s']
    )
    return _q(t)


def inventory_apply_batch_delta(
    *,
    customer_id: int,
    product_id: int | None,
    item_id: int | None,
    item_category_id: str,
    batch_no: str,
    mfg_date,
    exp_date,
    qty_delta,
    trn_date,
    last_trn_type: str,
    ref_doc_id: int | None,
    ref_doc_type: str,
    allow_create: bool = True,
) -> None:
    """
    Add qty_delta to ``InventoryStock`` for (customer, product or item, batch_no).

    **Open rows** (``is_closed=False``) are the live bucket: positive deltas merge
    duplicate open rows, update qty, and set ``is_closed=True`` when qty reaches zero.

    If no open row exists and ``qty_delta > 0`` with ``allow_create``, a **new** row
    is created even when **closed** rows share the same batch (new stock episode).

    If no open row and ``qty_delta < 0`` (e.g. document reversal), the delta is
    applied to the **latest** row for that key (by ``inv_id``); result qty cannot
    go below zero.

    ``opened_in_fy`` is set from ``trn_date`` on new rows and backfilled on
    existing rows when missing (merge / apply).
    """
    from .models import InventoryStock

    bn = (batch_no or '').strip()
    dq = _q(qty_delta)
    if dq == 0:
        return

    ref_date = trn_date or timezone.localdate()
    fy = get_or_create_financial_year_for_date(ref_date)

    flt: dict = {
        'customer_id': customer_id,
        'batch_no': bn,
    }
    if product_id:
        flt['product_id'] = product_id
        flt['item_id'] = None
    else:
        flt['item_id'] = item_id
        flt['product_id'] = None

    def _apply_to_row(row, delta: Decimal) -> None:
        new_qty = _q(row.qty + delta)
        if new_qty < 0:
            new_qty = _q(0)
        row.mfg_date = mfg_date
        row.exp_date = exp_date
        row.last_trn_date = trn_date
        row.last_trn_type = last_trn_type
        row.ref_doc_id = ref_doc_id
        row.ref_doc_type = ref_doc_type
        if new_qty <= 0:
            row.qty = _q(0)
            row.reserved_qty = _q(0)
            row.is_closed = True
        else:
            row.qty = new_qty
            row.is_closed = False
        upd = [
            'qty',
            'reserved_qty',
            'is_closed',
            'mfg_date',
            'exp_date',
            'last_trn_date',
            'last_trn_type',
            'ref_doc_id',
            'ref_doc_type',
        ]
        if row.opened_in_fy_id is None:
            row.opened_in_fy_id = fy.pk
            upd.append('opened_in_fy')
        row.save(update_fields=upd)

    open_qs = (
        InventoryStock.objects.select_for_update()
        .filter(**flt, is_closed=False)
        .order_by('inv_id')
    )
    open_rows = list(open_qs)

    if len(open_rows) > 1:
        keep = open_rows[0]
        total_qty = _q(sum(Decimal(str(r.qty or 0)) for r in open_rows))
        total_rsv = _q(sum(Decimal(str(r.reserved_qty or 0)) for r in open_rows))
        for r in open_rows[1:]:
            r.delete()
        keep.qty = total_qty
        if total_qty <= 0:
            keep.reserved_qty = _q(0)
            keep.is_closed = True
        else:
            keep.reserved_qty = total_rsv
            keep.is_closed = False
        merge_upd = ['qty', 'reserved_qty', 'is_closed']
        if keep.opened_in_fy_id is None:
            keep.opened_in_fy_id = fy.pk
            merge_upd.append('opened_in_fy')
        keep.save(update_fields=merge_upd)
        row_open = InventoryStock.objects.select_for_update().get(pk=keep.pk)
    elif len(open_rows) == 1:
        row_open = open_rows[0]
    else:
        row_open = None

    if row_open is not None:
        _apply_to_row(row_open, dq)
        return

    if dq > 0:
        if not allow_create:
            sku = f'product_id={product_id}' if product_id else f'item_id={item_id}'
            raise ValidationError(
                f'No open inventory row exists for this customer, {sku}, batch {bn!r}. '
                'Stock adjustments can only change existing open stock (use opening balance or inward to add new batches).',
                code='inv_adjust_no_row',
            )
        InventoryStock.objects.create(
            customer_id=customer_id,
            product_id=product_id,
            item_id=item_id,
            item_category_id=item_category_id,
            batch_no=bn,
            mfg_date=mfg_date,
            exp_date=exp_date,
            qty=dq,
            is_closed=False,
            opened_in_fy_id=fy.pk,
            last_trn_date=trn_date,
            last_trn_type=last_trn_type,
            ref_doc_id=ref_doc_id,
            ref_doc_type=ref_doc_type,
        )
        return

    # dq < 0, no open row: attach to latest row (reversals)
    row_any = (
        InventoryStock.objects.select_for_update()
        .filter(**flt)
        .order_by('-inv_id')
        .first()
    )
    if row_any is None:
        sku = f'product_id={product_id}' if product_id else f'item_id={item_id}'
        raise ValidationError(
            f'No inventory history for this customer, {sku}, batch {bn!r} to reverse.',
            code='inv_reverse_no_row',
        )
    _apply_to_row(row_any, dq)


def post_stock_adjustment_to_inventory(header: TrnStkAdjHed) -> None:
    """Apply all batch lines from a saved adjustment header to InventoryStock."""
    from .models import TrnStkAdjHed

    trn_type = (
        LAST_TRN_OPENING if header.stk_adj_type == TrnStkAdjHed.TYPE_OPENING else LAST_TRN_ADJUST
    )
    ref_id = header.pk
    allow_create = header.stk_adj_type == TrnStkAdjHed.TYPE_OPENING

    lines = header.lines.prefetch_related('batches').select_related('product', 'item')
    for line in lines:
        if line.product_id:
            cat_id = line.product.prod_category_id
            pid, iid = line.product_id, None
        else:
            cat_id = line.item.item_category_id
            pid, iid = None, line.item_id

        for b in line.batches.all():
            inventory_apply_batch_delta(
                customer_id=header.customer_id,
                product_id=pid,
                item_id=iid,
                item_category_id=cat_id,
                batch_no=b.batch_no,
                mfg_date=b.mfg_date,
                exp_date=b.exp_date,
                qty_delta=b.batch_qty,
                trn_date=header.stk_adj_dt,
                last_trn_type=trn_type,
                ref_doc_id=ref_id,
                ref_doc_type=REF_DOC_TYPE_STK_ADJ,
                allow_create=allow_create,
            )


def reverse_stock_adjustment_from_inventory(header: TrnStkAdjHed) -> None:
    """Undo ledger impact of this header (same batches with opposite sign)."""
    from .models import TrnStkAdjHed

    trn_type = (
        LAST_TRN_OPENING if header.stk_adj_type == TrnStkAdjHed.TYPE_OPENING else LAST_TRN_ADJUST
    )
    ref_id = header.pk

    lines = header.lines.prefetch_related('batches').select_related('product', 'item')
    for line in lines:
        if line.product_id:
            cat_id = line.product.prod_category_id
            pid, iid = line.product_id, None
        else:
            cat_id = line.item.item_category_id
            pid, iid = None, line.item_id

        for b in line.batches.all():
            inventory_apply_batch_delta(
                customer_id=header.customer_id,
                product_id=pid,
                item_id=iid,
                item_category_id=cat_id,
                batch_no=b.batch_no,
                mfg_date=b.mfg_date,
                exp_date=b.exp_date,
                qty_delta=-b.batch_qty,
                trn_date=header.stk_adj_dt,
                last_trn_type=trn_type,
                ref_doc_id=ref_id,
                ref_doc_type=REF_DOC_TYPE_STK_ADJ,
            )


def save_stock_adjustment_document(
    *,
    header_pk: int | None,
    customer_id: int,
    stk_adj_dt,
    stk_adj_type: str,
    item_type_id: int,
    remarks: str,
    lines_payload: list[dict],
) -> TrnStkAdjHed:
    """
    Create or replace header + lines from validated payload and post to InventoryStock.

    lines_payload entries:
        { 'kind': 'P'|'I', 'master_id': int, 'remarks': str,
          'batches': [ { 'batch_no', 'mfg_date', 'exp_date', 'batch_qty' }, ... ] }
    """
    from .models import TrnStkAdjDtl1, TrnStkAdjDtl2, TrnStkAdjHed

    with transaction.atomic():
        if header_pk:
            old = (
                TrnStkAdjHed.objects.select_for_update()
                .prefetch_related('lines__batches', 'lines__product', 'lines__item')
                .get(pk=header_pk)
            )
            reverse_stock_adjustment_from_inventory(old)
            old.lines.all().delete()

            hed = TrnStkAdjHed.objects.select_for_update().get(pk=header_pk)
            hed.customer_id = customer_id
            hed.stk_adj_dt = stk_adj_dt
            hed.stk_adj_type = stk_adj_type
            hed.item_type_id = item_type_id
            hed.remarks = remarks
            hed.save(
                update_fields=[
                    'customer_id',
                    'stk_adj_dt',
                    'stk_adj_type',
                    'item_type_id',
                    'remarks',
                ]
            )
        else:
            hed = TrnStkAdjHed.objects.create(
                customer_id=customer_id,
                stk_adj_dt=stk_adj_dt,
                stk_adj_type=stk_adj_type,
                item_type_id=item_type_id,
                remarks=remarks,
            )

        for row in lines_payload:
            kind = row['kind']
            mid = int(row['master_id'])
            line_remarks = (row.get('remarks') or '')[:20]
            batches = row['batches']

            if kind == 'P':
                d1 = TrnStkAdjDtl1.objects.create(
                    header=hed,
                    product_id=mid,
                    item=None,
                    quantity=Decimal('0'),
                    line_remarks=line_remarks,
                )
            else:
                d1 = TrnStkAdjDtl1.objects.create(
                    header=hed,
                    product=None,
                    item_id=mid,
                    quantity=Decimal('0'),
                    line_remarks=line_remarks,
                )

            total = Decimal('0')
            for b in batches:
                bq = _q(b['batch_qty'])
                total += bq
                TrnStkAdjDtl2.objects.create(
                    line=d1,
                    batch_no=(b.get('batch_no') or '').strip(),
                    mfg_date=b.get('mfg_date'),
                    exp_date=b.get('exp_date'),
                    batch_qty=bq,
                )
            d1.quantity = _q(total)
            d1.save(update_fields=['quantity'])

        hed = (
            TrnStkAdjHed.objects.prefetch_related('lines__batches', 'lines__product', 'lines__item')
            .get(pk=hed.pk)
        )
        post_stock_adjustment_to_inventory(hed)
        return hed


def delete_stock_adjustment_document(header: TrnStkAdjHed) -> None:
    with transaction.atomic():
        h = (
            TrnStkAdjHed.objects.select_for_update()
            .prefetch_related('lines__batches', 'lines__product', 'lines__item')
            .get(pk=header.pk)
        )
        reverse_stock_adjustment_from_inventory(h)
        h.delete()


def close_inventory_stock_opened_in_financial_year(fy) -> int:
    """
    Year-end: mark **exhausted** ledger rows (qty and reserved both zero) that
    were opened in ``fy`` as closed. Rows with remaining stock stay open even if
    first posted in that FY (stock can span financial years).

    Idempotent; does not change quantities.
    """
    from .models import InventoryStock

    return InventoryStock.objects.filter(
        opened_in_fy_id=fy.pk,
        is_closed=False,
        qty__lte=0,
        reserved_qty__lte=0,
    ).update(is_closed=True)
