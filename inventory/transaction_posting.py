"""
Post or reverse InventoryStock movements from transaction documents.

Call these from ``transactions`` forms/views inside ``transaction.atomic()``
after/before persistence so the ledger stays aligned with Trn* tables.

Business balance (conceptual; ``InventoryStock`` is the running bucket ledger):

- **Item (RM/PM, etc.):** Opening + Inward (net of item ``sample_qty``) − RM dispensing − PM dispensing/issues
  ± Adjustment. Wired today: Inward ``+``, RM dispensing ``-``, stock adjustment
  ``±``. PM dispensing/issues: hook when that transaction exists.

- **Product (FG):** Opening + DPR (sections that add FG — typically Blister,
  Pouching, Stripping, Bulk Packing) − **Sales invoice (FG dispatch)** ± Adjustment.
  DPR posting is gated by ``transactions.constants.DPR_FG_INVENTORY_SECTION_KEYWORDS``
  (empty = all working DPR rows). **Sales invoices** (``TrnSlsHed`` / ``TrnSlsDtl2``)
  post FG reductions via ``post_sales_invoice_to_inventory`` using log sheet batch keys.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from transactions.constants import DPR_FG_INVENTORY_SECTION_KEYWORDS, QTY_DECIMAL_PLACES
from transactions.models import (
    DPR_MACHINE_WORKING,
    TrnBatchDtl,
    TrnDpr,
    TrnInwHed,
    TrnInwDtl2,
    TrnlssDtl,
    TrnlssHed,
    TrnSlsDtl2,
    TrnSlsHed,
    _logsheet_parse_mmm_yyyy,
)

from .services import inventory_apply_batch_delta

REF_DOC_INW = 'INW'
REF_DOC_RM_DISP = 'RM_DISP'
REF_DOC_DPR = 'DPR'
REF_DOC_SLS_INV = 'SLS_INV'

LAST_TRN_INWARD = 'INWARD'
LAST_TRN_RM_DISP = 'RM_DISPENSE'
LAST_TRN_DPR = 'DPR'
LAST_TRN_SALES_INV = 'SALES_INV'


def _q_inv_qty(d) -> Decimal:
    step = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)
    return Decimal(str(d or 0)).quantize(step, rounding=ROUND_HALF_UP)


def _inward_item_inventory_postings(d1, hed: TrnInwHed):
    """
    Yields (batch_line_or_none, qty_to_inventory) for one inward Dtl1 line.

    ``qty_to_inventory`` is inward quantity minus the item master ``sample_qty``
    (sample is taken from the first batch lines in ``dtl2_id`` order until used up).
    ``batch_line_or_none`` is ``TrnInwDtl2`` when batching is used, else ``None``
    for a single no-batch bucket (empty batch key).
    """
    item = d1.item
    sample_cap = _q_inv_qty(getattr(item, 'sample_qty', 0) or 0)

    batches = list(
        TrnInwDtl2.objects.filter(inward=hed, item_id=d1.item_id).order_by('dtl2_id')
    )
    if batches:
        total_recv = _q_inv_qty(sum(_q_inv_qty(b.batch_qty) for b in batches))
        remaining_sample = _q_inv_qty(min(sample_cap, total_recv))
        for b in batches:
            q = _q_inv_qty(b.batch_qty)
            take = _q_inv_qty(min(q, remaining_sample))
            posted = _q_inv_qty(q - take)
            remaining_sample = _q_inv_qty(remaining_sample - take)
            if posted > 0:
                yield (b, posted)
    else:
        q = _q_inv_qty(d1.quantity)
        posted = _q_inv_qty(q - min(sample_cap, q))
        if posted > 0:
            yield (None, posted)


def _batch_dtl_mfg_exp_dates(batch_line: TrnBatchDtl | None) -> tuple[date | None, date | None]:
    if not batch_line:
        return None, None
    mfg, exp = None, None
    try:
        y, m, _ = _logsheet_parse_mmm_yyyy(batch_line.mfg_dt, 'MFG')
        mfg = date(y, m, 1)
    except (ValidationError, TypeError, ValueError):
        pass
    try:
        y, m, _ = _logsheet_parse_mmm_yyyy(batch_line.exp_dt, 'EXP')
        exp = date(y, m, 1)
    except (ValidationError, TypeError, ValueError):
        pass
    return mfg, exp


def post_inward_to_inventory(hed: TrnInwHed) -> None:
    """Add RM/PM stock from inward batch / line quantities (after item ``sample_qty``)."""
    cust_id = hed.customer_id
    trn_dt = hed.inward_dt
    ref_id = hed.pk

    d1_list = list(hed.lines.select_related('item', 'item__item_category'))
    for d1 in d1_list:
        item = d1.item
        cat_id = item.item_category_id
        for b, posted in _inward_item_inventory_postings(d1, hed):
            if b is not None:
                inventory_apply_batch_delta(
                    customer_id=cust_id,
                    product_id=None,
                    item_id=item.pk,
                    item_category_id=cat_id,
                    batch_no=b.batch_no,
                    mfg_date=b.mfg_dt,
                    exp_date=b.exp_dt,
                    qty_delta=posted,
                    trn_date=trn_dt,
                    last_trn_type=LAST_TRN_INWARD,
                    ref_doc_id=ref_id,
                    ref_doc_type=REF_DOC_INW,
                )
            else:
                inventory_apply_batch_delta(
                    customer_id=cust_id,
                    product_id=None,
                    item_id=item.pk,
                    item_category_id=cat_id,
                    batch_no='',
                    mfg_date=None,
                    exp_date=None,
                    qty_delta=posted,
                    trn_date=trn_dt,
                    last_trn_type=LAST_TRN_INWARD,
                    ref_doc_id=ref_id,
                    ref_doc_type=REF_DOC_INW,
                )


def reverse_inward_from_inventory(hed: TrnInwHed) -> None:
    """Undo ledger rows for this inward (same buckets and amounts as post, opposite sign)."""
    cust_id = hed.customer_id
    trn_dt = hed.inward_dt
    ref_id = hed.pk

    for d1 in hed.lines.select_related('item', 'item__item_category'):
        item = d1.item
        cat_id = item.item_category_id
        for b, posted in _inward_item_inventory_postings(d1, hed):
            if b is not None:
                inventory_apply_batch_delta(
                    customer_id=cust_id,
                    product_id=None,
                    item_id=item.pk,
                    item_category_id=cat_id,
                    batch_no=b.batch_no,
                    mfg_date=b.mfg_dt,
                    exp_date=b.exp_dt,
                    qty_delta=-posted,
                    trn_date=trn_dt,
                    last_trn_type=LAST_TRN_INWARD,
                    ref_doc_id=ref_id,
                    ref_doc_type=REF_DOC_INW,
                )
            else:
                inventory_apply_batch_delta(
                    customer_id=cust_id,
                    product_id=None,
                    item_id=item.pk,
                    item_category_id=cat_id,
                    batch_no='',
                    mfg_date=None,
                    exp_date=None,
                    qty_delta=-posted,
                    trn_date=trn_dt,
                    last_trn_type=LAST_TRN_INWARD,
                    ref_doc_id=ref_id,
                    ref_doc_type=REF_DOC_INW,
                )


def _rm_line_issue_total(ln: TrnlssDtl) -> Decimal:
    q = Decimal(str(ln.issue_qty or 0)) + Decimal(str(ln.issue_add_qty or 0))
    step = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)
    return q.quantize(step)


def post_rm_dispensing_to_inventory(hed: TrnlssHed) -> None:
    """
    Deduct RM for saved dispensing lines only (standard ``issue_qty`` + ``issue_add_qty``).

    Lines are created only for BOM stages selected on the form; orphaned detail rows
    are removed on save so unchecked stages are not posted.
    """
    cust_id = hed.customer_id
    ref_id = hed.pk
    for ln in hed.lines.select_related('item', 'item__item_category'):
        tot = _rm_line_issue_total(ln)
        if tot <= 0:
            continue
        item = ln.item
        inventory_apply_batch_delta(
            customer_id=cust_id,
            product_id=None,
            item_id=item.pk,
            item_category_id=item.item_category_id,
            batch_no='',
            mfg_date=None,
            exp_date=None,
            qty_delta=-tot,
            trn_date=ln.issue_date,
            last_trn_type=LAST_TRN_RM_DISP,
            ref_doc_id=ref_id,
            ref_doc_type=REF_DOC_RM_DISP,
        )


def reverse_rm_dispensing_from_inventory(hed: TrnlssHed) -> None:
    for ln in hed.lines.select_related('item', 'item__item_category'):
        tot = _rm_line_issue_total(ln)
        if tot <= 0:
            continue
        item = ln.item
        inventory_apply_batch_delta(
            customer_id=hed.customer_id,
            product_id=None,
            item_id=item.pk,
            item_category_id=item.item_category_id,
            batch_no='',
            mfg_date=None,
            exp_date=None,
            qty_delta=tot,
            trn_date=ln.issue_date,
            last_trn_type=LAST_TRN_RM_DISP,
            ref_doc_id=hed.pk,
            ref_doc_type=REF_DOC_RM_DISP,
        )


def _dpr_production_lac(row: TrnDpr) -> Decimal:
    if row.batch_size_lakh is not None and row.batch_size_lakh > 0:
        return Decimal(str(row.batch_size_lakh))
    if row.section_qty is not None and row.section_qty > 0:
        return Decimal(str(row.section_qty))
    if row.batch_line_id and row.batch_line:
        bl = row.batch_line
        bn = int(bl.batch_qty_n or 0)
        if bn > 0 and row.qty_nos:
            return (Decimal(int(row.qty_nos)) / Decimal(bn)) * Decimal(str(bl.batch_qty_l))
    if row.qty_nos:
        return Decimal(int(row.qty_nos)) / Decimal(100000)
    return Decimal('0')


def _dpr_posting_batch_key(row: TrnDpr) -> tuple[str, date | None, date | None]:
    if row.batch_line_id and row.batch_line:
        bl = row.batch_line
        mfg, exp = _batch_dtl_mfg_exp_dates(bl)
        return bl.batch_no, mfg, exp
    return f'~DPR{row.pk}~', None, None


def _dpr_section_contributes_fg_inventory(section) -> bool:
    """
    When ``DPR_FG_INVENTORY_SECTION_KEYWORDS`` is non-empty, only DPR rows whose
    section name (spaces stripped, upper case) contains any keyword substring
    post FG to the ledger. Empty tuple = every working DPR row (legacy behaviour).
    Rows without a section do not post when filtering is enabled.
    """
    kws = DPR_FG_INVENTORY_SECTION_KEYWORDS or ()
    if not kws:
        return True
    if section is None:
        return False
    name = re.sub(r'\s+', '', (getattr(section, 'section_name', None) or '').upper())
    if not name:
        return False
    for k in kws:
        if re.sub(r'\s+', '', (k or '').upper()) in name:
            return True
    return False


def post_dpr_production_to_inventory(row: TrnDpr) -> None:
    """Increase FG stock from a working DPR row (optionally section-filtered)."""
    if row.machine_working != DPR_MACHINE_WORKING:
        return
    if not row.customer_id or not row.product_id:
        return
    if not _dpr_section_contributes_fg_inventory(getattr(row, 'section', None)):
        return
    lac = _dpr_production_lac(row)
    step = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)
    lac = lac.quantize(step)
    if lac <= 0:
        return
    prod = row.product
    bno, mfg, exp = _dpr_posting_batch_key(row)
    inventory_apply_batch_delta(
        customer_id=row.customer_id,
        product_id=prod.pk,
        item_id=None,
        item_category_id=prod.prod_category_id,
        batch_no=bno,
        mfg_date=mfg,
        exp_date=exp,
        qty_delta=lac,
        trn_date=row.trn_dpr_dt,
        last_trn_type=LAST_TRN_DPR,
        ref_doc_id=row.pk,
        ref_doc_type=REF_DOC_DPR,
    )


def reverse_dpr_production_from_inventory(row: TrnDpr) -> None:
    """Undo FG posting for this DPR row (uses current row field values)."""
    if row.machine_working != DPR_MACHINE_WORKING:
        return
    if not row.customer_id or not row.product_id:
        return
    if not _dpr_section_contributes_fg_inventory(getattr(row, 'section', None)):
        return
    lac = _dpr_production_lac(row)
    step = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)
    lac = lac.quantize(step)
    if lac <= 0:
        return
    prod = row.product
    bno, mfg, exp = _dpr_posting_batch_key(row)
    inventory_apply_batch_delta(
        customer_id=row.customer_id,
        product_id=prod.pk,
        item_id=None,
        item_category_id=prod.prod_category_id,
        batch_no=bno,
        mfg_date=mfg,
        exp_date=exp,
        qty_delta=-lac,
        trn_date=row.trn_dpr_dt,
        last_trn_type=LAST_TRN_DPR,
        ref_doc_id=row.pk,
        ref_doc_type=REF_DOC_DPR,
    )


def post_sales_invoice_to_inventory(hed: TrnSlsHed) -> None:
    """Reduce FG stock for each invoice batch line (log sheet → physical batch no.)."""
    cust_id = hed.customer_id
    trn_dt = hed.invoice_dt
    ref_id = hed.pk

    for d2 in (
        TrnSlsDtl2.objects.filter(invoice_line__invoice=hed)
        .select_related('invoice_line__product', 'log_sheet__batch_line')
        .order_by('dtl2_id')
    ):
        prod = d2.invoice_line.product
        bl = d2.log_sheet.batch_line
        if not bl:
            continue
        mfg, exp = _batch_dtl_mfg_exp_dates(bl)
        posted = _q_inv_qty(d2.batch_qty)
        if posted <= 0:
            continue
        inventory_apply_batch_delta(
            customer_id=cust_id,
            product_id=prod.pk,
            item_id=None,
            item_category_id=prod.prod_category_id,
            batch_no=bl.batch_no,
            mfg_date=mfg,
            exp_date=exp,
            qty_delta=-posted,
            trn_date=trn_dt,
            last_trn_type=LAST_TRN_SALES_INV,
            ref_doc_id=ref_id,
            ref_doc_type=REF_DOC_SLS_INV,
        )


def reverse_sales_invoice_from_inventory(hed: TrnSlsHed) -> None:
    """Restore FG stock removed by this invoice (same buckets as post)."""
    cust_id = hed.customer_id
    trn_dt = hed.invoice_dt
    ref_id = hed.pk

    for d2 in (
        TrnSlsDtl2.objects.filter(invoice_line__invoice=hed)
        .select_related('invoice_line__product', 'log_sheet__batch_line')
        .order_by('dtl2_id')
    ):
        prod = d2.invoice_line.product
        bl = d2.log_sheet.batch_line
        if not bl:
            continue
        mfg, exp = _batch_dtl_mfg_exp_dates(bl)
        posted = _q_inv_qty(d2.batch_qty)
        if posted <= 0:
            continue
        inventory_apply_batch_delta(
            customer_id=cust_id,
            product_id=prod.pk,
            item_id=None,
            item_category_id=prod.prod_category_id,
            batch_no=bl.batch_no,
            mfg_date=mfg,
            exp_date=exp,
            qty_delta=posted,
            trn_date=trn_dt,
            last_trn_type=LAST_TRN_SALES_INV,
            ref_doc_id=ref_id,
            ref_doc_type=REF_DOC_SLS_INV,
        )
