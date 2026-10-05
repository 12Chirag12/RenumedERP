"""
Dedicated central inventory ledger service for StockHed and StockDtl.

Handles all additions, issues, opening balances, reversals, and idempotency
with atomic locking (select_for_update) and negative stock prevention.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from transactions.constants import QTY_DECIMAL_PLACES
from transactions.utils import get_or_create_financial_year_for_date

if TYPE_CHECKING:
    from masters.models import FinancialYear
    from transactions.models import TrnDpr, TrnInwHed, TrnlssHed, TrnSlsHed
    from .models import TrnStkAdjHed

from .models import StockDtl, StockHed

_QUANT = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)


def _q(d) -> Decimal:
    return Decimal(str(d or 0)).quantize(_QUANT, rounding=ROUND_HALF_UP)


def get_item_closing_balance(
    customer_id: int,
    item_id: int,
    financial_year: FinancialYear | None = None,
) -> Decimal:
    """Sum closing_qty for an item across open StockHed rows (or specific FY)."""
    from django.db.models import Sum

    qs = StockHed.objects.filter(
        customer_id=customer_id,
        item_id=item_id,
        product_id__isnull=True,
        is_closed=False,
    )
    if financial_year:
        qs = qs.filter(financial_year=financial_year)
    total = qs.aggregate(s=Sum('closing_qty'))['s']
    return _q(total)


def get_fg_closing_balance(
    customer_id: int,
    product_id: int,
    batch_no: str,
    financial_year: FinancialYear | None = None,
) -> Decimal:
    """Sum closing_qty for a product batch across open StockHed rows (or specific FY)."""
    from django.db.models import Sum

    bn = (batch_no or '').strip()
    qs = StockHed.objects.filter(
        customer_id=customer_id,
        product_id=product_id,
        batch_no=bn,
        item_id__isnull=True,
        is_closed=False,
    )
    if financial_year:
        qs = qs.filter(financial_year=financial_year)
    total = qs.aggregate(s=Sum('closing_qty'))['s']
    return _q(total)


def compute_periodic_stock_movements(
    stock_hed_ids: list[int],
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[int, dict[str, Decimal]]:
    """
    Calculate opening, receipt, issue, and closing quantities for a set of StockHed IDs
    over an optional [from_date, to_date] window using StockDtl movements.
    """
    from collections import defaultdict
    res: dict[int, dict[str, Decimal]] = defaultdict(lambda: {
        'opening_qty': Decimal('0'),
        'receipt_qty': Decimal('0'),
        'issue_qty': Decimal('0'),
        'closing_qty': Decimal('0'),
    })

    if not stock_hed_ids:
        return res

    qs = StockDtl.objects.filter(stock_id__in=stock_hed_ids)
    if to_date:
        qs = qs.filter(trn_date__lte=to_date)

    for m in qs.only('stock_id', 'trn_type', 'trn_date', 'quantity', 'is_reversal'):
        sid = m.stock_id
        sign = Decimal('-1') if m.is_reversal else Decimal('1')
        qty = _q(m.quantity) * sign

        if from_date and m.trn_date < from_date:
            if m.trn_type in (StockDtl.TYPE_OPENING, StockDtl.TYPE_RECEIPT):
                res[sid]['opening_qty'] = _q(res[sid]['opening_qty'] + qty)
            else:
                res[sid]['opening_qty'] = _q(res[sid]['opening_qty'] - qty)
        else:
            if m.trn_type == StockDtl.TYPE_OPENING:
                if from_date is None:
                    res[sid]['opening_qty'] = _q(res[sid]['opening_qty'] + qty)
                else:
                    res[sid]['receipt_qty'] = _q(res[sid]['receipt_qty'] + qty)
            elif m.trn_type == StockDtl.TYPE_RECEIPT:
                res[sid]['receipt_qty'] = _q(res[sid]['receipt_qty'] + qty)
            else:
                res[sid]['issue_qty'] = _q(res[sid]['issue_qty'] + qty)

    for sid in stock_hed_ids:
        d = res[sid]
        d['closing_qty'] = _q(d['opening_qty'] + d['receipt_qty'] - d['issue_qty'])

    return res


def post_stock_movement(
    *,
    customer_id: int,
    product_id: int | None,
    item_id: int | None,
    batch_no: str = '',
    mfg_date: date | None = None,
    exp_date: date | None = None,
    quantity: Decimal | str | float,
    tran_id: str,
    trn_type: str,
    trn_no: str,
    trn_date: date | None,
    source_line_id: str,
    financial_year: FinancialYear | None = None,
    remarks: str = '',
    allow_create: bool = True,
) -> StockDtl:
    """
    Post a stock movement row atomically and update StockHed running totals.

    - Locks StockHed with select_for_update().
    - Validates SKU: exactly one of product_id or item_id must be set.
    - RM/PM: item-wise only, batch_no is forced empty, mfg/exp date is None.
    - FG: product-and-batch-wise.
    - Enforces closing_qty = opn_qty + rcpt_qty - issue_qty.
    - Prevents negative closing stock.
    - Idempotent: repeated calls with the same active source_line_id return existing StockDtl.
    """
    qty = _q(quantity)
    if qty <= 0:
        raise ValidationError(
            f'Stock movement quantity must be greater than zero (received {qty}).',
            code='invalid_qty',
        )

    if bool(product_id) == bool(item_id):
        raise ValidationError(
            'Exactly one of product_id or item_id must be provided for stock posting.',
            code='invalid_sku',
        )

    trn_dt = trn_date or timezone.localdate()
    fy = financial_year or get_or_create_financial_year_for_date(trn_dt)

    if item_id:
        bn = ''
        m_dt = None
        e_dt = None
    else:
        bn = (batch_no or '').strip()
        if not bn:
            raise ValidationError(
                'Batch number is required for finished goods stock posting.',
                code='missing_batch_no',
            )
        m_dt = mfg_date
        e_dt = exp_date

    with transaction.atomic():
        # Check idempotency first: if an active (unreversed) movement exists for this source_line_id, do not double-post.
        existing_move = (
            StockDtl.objects.select_for_update()
            .filter(source_line_id=source_line_id, is_reversal=False)
            .first()
        )
        if existing_move:
            # Check if this movement is active (not reversed)
            if not existing_move.reversals.exists():
                return existing_move
            # If it was reversed previously, a repost requires a unique sequence/version if unique constraint is hit.
            # We will handle re-post below.

        flt: dict = {
            'financial_year': fy,
            'customer_id': customer_id,
        }
        if item_id:
            flt['item_id'] = item_id
            flt['product_id__isnull'] = True
        else:
            flt['product_id'] = product_id
            flt['batch_no'] = bn
            flt['item_id__isnull'] = True

        stock_hed = StockHed.objects.select_for_update().filter(**flt).first()

        if stock_hed is None:
            if not allow_create and trn_type == StockDtl.TYPE_ISSUE:
                sku_lbl = f'product_id={product_id} batch={bn!r}' if product_id else f'item_id={item_id}'
                raise ValidationError(
                    f'No stock balance exists for customer {customer_id}, {sku_lbl} to issue.',
                    code='no_stock_row',
                )

            # Resolve item_category_id
            cat_id = None
            if item_id:
                from masters.models import MstItem
                it = MstItem.objects.filter(pk=item_id).values_list('item_category_id', flat=True).first()
                cat_id = it
            else:
                from masters.models import MstProd
                pr = MstProd.objects.filter(pk=product_id).values_list('prod_category_id', flat=True).first()
                cat_id = pr

            try:
                stock_hed = StockHed.objects.create(
                    op_date=trn_dt,
                    financial_year=fy,
                    customer_id=customer_id,
                    item_id=item_id,
                    product_id=product_id,
                    item_category_id=cat_id,
                    batch_no=bn,
                    mfg_date=m_dt,
                    exp_date=e_dt,
                    opn_qty=Decimal('0'),
                    rcpt_qty=Decimal('0'),
                    issue_qty=Decimal('0'),
                    closing_qty=Decimal('0'),
                    reserved_qty=Decimal('0'),
                    is_closed=False,
                    last_trn_date=trn_dt,
                    last_trn_type=f'{tran_id}/{trn_type}',
                )
                stock_hed = StockHed.objects.select_for_update().get(pk=stock_hed.pk)
            except IntegrityError:
                # Concurrent create race condition
                stock_hed = StockHed.objects.select_for_update().filter(**flt).first()
                if stock_hed is None:
                    raise

        # Check negative stock on issue
        if trn_type == StockDtl.TYPE_ISSUE:
            if stock_hed.closing_qty - qty < Decimal('0'):
                sku_desc = (
                    f'product {product_id} batch {bn!r}'
                    if product_id
                    else f'item {item_id}'
                )
                raise ValidationError(
                    f'Insufficient stock for {sku_desc}: available {stock_hed.closing_qty}, required {qty}.',
                    code='insufficient_stock',
                )
            stock_hed.issue_qty = _q(stock_hed.issue_qty + qty)
        elif trn_type == StockDtl.TYPE_RECEIPT:
            stock_hed.rcpt_qty = _q(stock_hed.rcpt_qty + qty)
        elif trn_type == StockDtl.TYPE_OPENING:
            stock_hed.opn_qty = _q(stock_hed.opn_qty + qty)
        else:
            raise ValidationError(f'Invalid trn_type: {trn_type!r}. Must be O, R, or I.', code='invalid_trn_type')

        stock_hed.closing_qty = stock_hed.calculate_closing_qty()
        if stock_hed.closing_qty < Decimal('0'):
            raise ValidationError(
                f'Posting would result in negative closing stock ({stock_hed.closing_qty}).',
                code='negative_closing_stock',
            )

        stock_hed.is_closed = (stock_hed.closing_qty == Decimal('0') and _q(stock_hed.reserved_qty) == Decimal('0'))
        if m_dt and not stock_hed.mfg_date:
            stock_hed.mfg_date = m_dt
        if e_dt and not stock_hed.exp_date:
            stock_hed.exp_date = e_dt
        stock_hed.last_trn_date = trn_dt
        stock_hed.last_trn_type = f'{tran_id}/{trn_type}'

        stock_hed.save(
            update_fields=[
                'opn_qty',
                'rcpt_qty',
                'issue_qty',
                'closing_qty',
                'is_closed',
                'mfg_date',
                'exp_date',
                'last_trn_date',
                'last_trn_type',
                'updated_at',
            ]
        )

        # Unique key check for re-posted lines after previous reversal:
        final_source_id = source_line_id
        if StockDtl.objects.filter(source_line_id=final_source_id).exists():
            # If a reversed record already exists with this key, add suffix for the new posting
            count = StockDtl.objects.filter(source_line_id__startswith=f'{source_line_id}#').count() + 2
            final_source_id = f'{source_line_id}#{count}'

        dtl = StockDtl.objects.create(
            stock=stock_hed,
            tran_id=tran_id,
            trn_type=trn_type,
            trn_no=trn_no,
            trn_date=trn_dt,
            quantity=qty,
            source_line_id=final_source_id,
            is_reversal=False,
            remarks=remarks,
        )
        return dtl


def reverse_stock_movement(
    *,
    source_line_id: str,
    trn_date: date | None = None,
    remarks: str = '',
) -> list[StockDtl]:
    """
    Atomically reverse an existing movement by creating a compensating StockDtl row
    and adjusting StockHed running totals without deleting history.

    - Idempotent: if already reversed or never posted, returns empty list.
    - Prevents negative closing stock on Receipt / Opening reversals.
    """
    with transaction.atomic():
        candidates = list(
            StockDtl.objects.select_for_update()
            .filter(source_line_id=source_line_id, is_reversal=False)
            .order_by('stock_dtl_id')
        )
        if not candidates:
            # Also check if it was given a suffixed key e.g. "DPR-5#2"
            candidates = list(
                StockDtl.objects.select_for_update()
                .filter(source_line_id__startswith=f'{source_line_id}#', is_reversal=False)
                .order_by('stock_dtl_id')
            )

        active_moves = [m for m in candidates if not m.reversals.exists()]
        if not active_moves:
            return []

        reversal_rows: list[StockDtl] = []
        rev_dt = trn_date or timezone.localdate()

        for original in active_moves:
            stock_hed = StockHed.objects.select_for_update().get(pk=original.stock_id)

            if original.trn_type in (StockDtl.TYPE_RECEIPT, StockDtl.TYPE_OPENING):
                # Reversing a receipt or opening decreases closing stock
                if stock_hed.closing_qty - original.quantity < Decimal('0'):
                    raise ValidationError(
                        f'Cannot reverse {original.source_line_id}: stock closing balance '
                        f'would become negative ({stock_hed.closing_qty - original.quantity}).',
                        code='reversal_causes_negative_stock',
                    )
                if original.trn_type == StockDtl.TYPE_RECEIPT:
                    stock_hed.rcpt_qty = _q(stock_hed.rcpt_qty - original.quantity)
                else:
                    stock_hed.opn_qty = _q(stock_hed.opn_qty - original.quantity)
            elif original.trn_type == StockDtl.TYPE_ISSUE:
                # Reversing an issue decreases issue_qty, increasing closing stock
                stock_hed.issue_qty = _q(stock_hed.issue_qty - original.quantity)

            stock_hed.closing_qty = stock_hed.calculate_closing_qty()
            if stock_hed.closing_qty < Decimal('0'):
                raise ValidationError(
                    f'Reversal would result in negative closing stock ({stock_hed.closing_qty}).',
                    code='negative_closing_stock',
                )

            stock_hed.is_closed = (
                stock_hed.closing_qty == Decimal('0') and _q(stock_hed.reserved_qty) == Decimal('0')
            )
            stock_hed.last_trn_date = rev_dt
            stock_hed.last_trn_type = f'REV/{original.tran_id}'
            stock_hed.save(
                update_fields=[
                    'opn_qty',
                    'rcpt_qty',
                    'issue_qty',
                    'closing_qty',
                    'is_closed',
                    'last_trn_date',
                    'last_trn_type',
                    'updated_at',
                ]
            )

            rev_source_id = f'REV:{original.source_line_id}'
            if StockDtl.objects.filter(source_line_id=rev_source_id).exists():
                count = StockDtl.objects.filter(source_line_id__startswith=f'{rev_source_id}#').count() + 2
                rev_source_id = f'{rev_source_id}#{count}'

            rev_row = StockDtl.objects.create(
                stock=stock_hed,
                tran_id=original.tran_id,
                trn_type=original.trn_type,
                trn_no=original.trn_no,
                trn_date=rev_dt,
                quantity=original.quantity,
                source_line_id=rev_source_id,
                is_reversal=True,
                reversal_of=original,
                remarks=remarks or f'Reversal of {original.source_line_id}',
            )
            reversal_rows.append(rev_row)

        return reversal_rows


# -------------------------------------------------------------------------
# Document-Level Post and Reverse Functions
# -------------------------------------------------------------------------


def post_inward_ledger(hed: TrnInwHed) -> None:
    """Post RM/PM inward lines to StockHed and StockDtl (INW / R, unbatched)."""
    cust_id = hed.customer_id
    trn_dt = getattr(hed, 'inward_dt', None)
    grn_no = getattr(hed, 'grn_no', None) or str(getattr(hed, 'pk', ''))

    lines = hed.lines.all()
    if hasattr(lines, 'select_related'):
        lines = lines.select_related('item')
    if hasattr(lines, 'order_by'):
        lines = lines.order_by('dtl1_id')

    for d1 in lines:
        item = d1.item
        sample_cap = _q(getattr(item, 'sample_qty', 0) or 0)
        received = _q(d1.quantity)
        posted = _q(received - min(sample_cap, received))
        if posted <= 0:
            continue

        source_id = f'INW:{d1.pk}'
        post_stock_movement(
            customer_id=cust_id,
            product_id=None,
            item_id=item.pk,
            batch_no='',
            mfg_date=None,
            exp_date=None,
            quantity=posted,
            tran_id=StockDtl.TRAN_INW,
            trn_type=StockDtl.TYPE_RECEIPT,
            trn_no=grn_no,
            trn_date=trn_dt,
            source_line_id=source_id,
            remarks=f'Inward GRN {grn_no}',
        )


def reverse_inward_ledger(hed: TrnInwHed) -> None:
    """Reverse inward movements from StockHed and StockDtl."""
    trn_dt = hed.inward_dt
    for d1 in hed.lines.all():
        source_id = f'INW:{d1.pk}'
        reverse_stock_movement(
            source_line_id=source_id,
            trn_date=trn_dt,
            remarks=f'Reversal of Inward GRN {hed.grn_no or hed.pk}',
        )


def post_rm_dispensing_ledger(hed: TrnlssHed) -> None:
    """Post RM dispensing issues to StockHed and StockDtl (DIS / I, unbatched)."""
    cust_id = hed.customer_id
    doc_no = f'DISP-{hed.pk}'

    lines = hed.lines.all()
    if hasattr(lines, 'select_related'):
        lines = lines.select_related('item')
    if hasattr(lines, 'order_by'):
        lines = lines.order_by('dtl_id')

    for ln in lines:
        tot = _q(Decimal(str(ln.issue_qty or 0)) + Decimal(str(ln.issue_add_qty or 0)))
        if tot <= 0:
            continue
        source_id = f'DIS:{ln.pk}'
        post_stock_movement(
            customer_id=cust_id,
            product_id=None,
            item_id=ln.item_id,
            batch_no='',
            mfg_date=None,
            exp_date=None,
            quantity=tot,
            tran_id=StockDtl.TRAN_DIS,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no=doc_no,
            trn_date=ln.issue_date or hed.dispensing_dt,
            source_line_id=source_id,
            remarks=f'Dispensing #{hed.pk}',
            allow_create=False,
        )


def reverse_rm_dispensing_ledger(hed: TrnlssHed) -> None:
    """Reverse RM dispensing issues from StockHed and StockDtl."""
    for ln in hed.lines.all():
        source_id = f'DIS:{ln.pk}'
        reverse_stock_movement(
            source_line_id=source_id,
            trn_date=ln.issue_date or hed.dispensing_dt,
            remarks=f'Reversal of Dispensing #{hed.pk}',
        )


def post_dpr_ledger(row: TrnDpr) -> None:
    """Post finished goods production from DPR to StockHed and StockDtl (DPR / R)."""
    from transactions.models import DPR_MACHINE_WORKING
    from .transaction_posting import (
        _dpr_posting_batch_key,
        _dpr_production_lac,
        _dpr_section_contributes_fg_inventory,
    )

    if row.machine_working != DPR_MACHINE_WORKING:
        return
    if not row.customer_id or not row.product_id:
        return
    if not _dpr_section_contributes_fg_inventory(getattr(row, 'section', None)):
        return

    lac = _q(_dpr_production_lac(row))
    if lac <= 0:
        return

    bno, mfg, exp = _dpr_posting_batch_key(row)
    source_id = f'DPR:{row.pk}'

    post_stock_movement(
        customer_id=row.customer_id,
        product_id=row.product_id,
        item_id=None,
        batch_no=bno,
        mfg_date=mfg,
        exp_date=exp,
        quantity=lac,
        tran_id=StockDtl.TRAN_DPR,
        trn_type=StockDtl.TYPE_RECEIPT,
        trn_no=f'DPR-{row.pk}',
        trn_date=row.trn_dpr_dt,
        source_line_id=source_id,
        remarks=f'DPR #{row.pk} production',
    )


def reverse_dpr_ledger(row: TrnDpr) -> None:
    """Reverse finished goods production from DPR in StockHed and StockDtl."""
    source_id = f'DPR:{row.pk}'
    reverse_stock_movement(
        source_line_id=source_id,
        trn_date=row.trn_dpr_dt,
        remarks=f'Reversal of DPR #{row.pk}',
    )


def post_sales_invoice_ledger(hed: TrnSlsHed) -> None:
    """Post finished goods dispatch from Sales Invoice to StockHed and StockDtl (SLS / I)."""
    from transactions.models import TrnSlsDtl2
    from .transaction_posting import _batch_dtl_mfg_exp_dates

    cust_id = hed.customer_id
    trn_dt = hed.invoice_dt
    inv_no = hed.invoice_no

    for d2 in (
        TrnSlsDtl2.objects.filter(invoice_line__invoice=hed)
        .select_related('invoice_line__product', 'log_sheet__batch_line')
        .order_by('dtl2_id')
    ):
        prod = d2.invoice_line.product
        bl = d2.log_sheet.batch_line if d2.log_sheet else None
        if not bl or not bl.batch_no:
            continue
        mfg, exp = _batch_dtl_mfg_exp_dates(bl)
        posted = _q(d2.batch_qty)
        if posted <= 0:
            continue

        source_id = f'SLS:{d2.pk}'
        post_stock_movement(
            customer_id=cust_id,
            product_id=prod.pk,
            item_id=None,
            batch_no=bl.batch_no,
            mfg_date=mfg,
            exp_date=exp,
            quantity=posted,
            tran_id=StockDtl.TRAN_SLS,
            trn_type=StockDtl.TYPE_ISSUE,
            trn_no=inv_no,
            trn_date=trn_dt,
            source_line_id=source_id,
            remarks=f'Sales Invoice {inv_no}',
            allow_create=False,
        )


def reverse_sales_invoice_ledger(hed: TrnSlsHed) -> None:
    """Reverse finished goods dispatch from Sales Invoice in StockHed and StockDtl."""
    from transactions.models import TrnSlsDtl2

    trn_dt = hed.invoice_dt
    for d2 in TrnSlsDtl2.objects.filter(invoice_line__invoice=hed):
        source_id = f'SLS:{d2.pk}'
        reverse_stock_movement(
            source_line_id=source_id,
            trn_date=trn_dt,
            remarks=f'Reversal of Sales Invoice {hed.invoice_no}',
        )


def post_stock_adjustment_ledger(header: TrnStkAdjHed) -> None:
    """Post stock adjustment or opening document to StockHed and StockDtl."""
    from .models import TrnStkAdjHed

    is_opening = header.stk_adj_type == TrnStkAdjHed.TYPE_OPENING
    tran_id = StockDtl.TRAN_OPN if is_opening else StockDtl.TRAN_STK
    doc_no = f'STKADJ-{header.pk}'
    trn_dt = header.stk_adj_dt
    cust_id = header.customer_id

    lines = header.lines.prefetch_related('batches').select_related('product', 'item').order_by('dtl1_id')
    for line in lines:
        pid = line.product_id
        iid = line.item_id

        for b in line.batches.all().order_by('dtl2_id'):
            bq = _q(b.batch_qty)
            if bq == Decimal('0'):
                continue

            if is_opening:
                trn_type = StockDtl.TYPE_OPENING
                quantity = bq
            elif bq > Decimal('0'):
                trn_type = StockDtl.TYPE_RECEIPT
                quantity = bq
            else:
                trn_type = StockDtl.TYPE_ISSUE
                quantity = abs(bq)

            source_id = f'{tran_id}:{b.pk}'
            post_stock_movement(
                customer_id=cust_id,
                product_id=pid,
                item_id=iid,
                batch_no=b.batch_no if pid else '',
                mfg_date=b.mfg_date if pid else None,
                exp_date=b.exp_date if pid else None,
                quantity=quantity,
                tran_id=tran_id,
                trn_type=trn_type,
                trn_no=doc_no,
                trn_date=trn_dt,
                source_line_id=source_id,
                remarks=f'Stock {"Opening" if is_opening else "Adjustment"} #{header.pk}',
                allow_create=is_opening or trn_type == StockDtl.TYPE_RECEIPT,
            )


def reverse_stock_adjustment_ledger(header: TrnStkAdjHed) -> None:
    """Reverse stock adjustment or opening document from StockHed and StockDtl."""
    from .models import TrnStkAdjHed

    is_opening = header.stk_adj_type == TrnStkAdjHed.TYPE_OPENING
    tran_id = StockDtl.TRAN_OPN if is_opening else StockDtl.TRAN_STK
    trn_dt = header.stk_adj_dt

    lines = header.lines.prefetch_related('batches').all()
    for line in lines:
        for b in line.batches.all():
            source_id = f'{tran_id}:{b.pk}'
            reverse_stock_movement(
                source_line_id=source_id,
                trn_date=trn_dt,
                remarks=f'Reversal of Stock {"Opening" if is_opening else "Adjustment"} #{header.pk}',
            )
