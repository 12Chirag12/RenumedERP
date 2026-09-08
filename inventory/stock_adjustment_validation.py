"""
Parse and validate stock adjustment JSON payload (header + lines + batches).
"""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.utils.dateparse import parse_date

from masters.models import MstCustProd, MstItem, MstItemType, MstProd
from transactions.constants import QTY_DECIMAL_PLACES

from .models import InventoryStock, TrnStkAdjHed

_QUANT = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)


def _q(d) -> Decimal:
    return Decimal(str(d or 0)).quantize(_QUANT, rounding=ROUND_HALF_UP)


def parse_stock_adjustment_body(raw: str) -> tuple[list[str], dict[str, Any] | None]:
    """Parse JSON body; return (errors, data) where data is ready for validate()."""
    if not (raw or '').strip():
        return (['Document lines are required.'], None)
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return (['Invalid JSON in lines field.'], None)
    if not isinstance(body, dict):
        return (['Lines payload must be a JSON object.'], None)
    return ([], body)


def validate_stock_adjustment_payload(
    body: dict[str, Any],
    *,
    edit_pk: int | None,
) -> tuple[list[str], dict[str, Any] | None]:
    """
    Validate business rules. Returns (errors, cleaned) where cleaned matches
    save_stock_adjustment_document(...) kwargs lines_payload structure.
    """
    errors: list[str] = []

    customer_id = body.get('customer_id')
    stk_adj_dt_raw = body.get('stk_adj_dt')
    stk_adj_type = (body.get('stk_adj_type') or '').strip().upper()
    item_type_id = body.get('item_type_id')
    remarks = (body.get('remarks') or '').strip()
    lines_in = body.get('lines')

    try:
        customer_id = int(customer_id)
    except (TypeError, ValueError):
        customer_id = 0
    if customer_id <= 0:
        errors.append('Select a valid customer.')

    d = parse_date(str(stk_adj_dt_raw or '').strip()) if stk_adj_dt_raw else None
    if not d:
        errors.append('Document date is required.')

    if stk_adj_type not in (TrnStkAdjHed.TYPE_OPENING, TrnStkAdjHed.TYPE_ADJUST):
        errors.append('Select opening balance or stock adjustment.')

    try:
        item_type_id = int(item_type_id)
    except (TypeError, ValueError):
        item_type_id = 0
    item_type = MstItemType.objects.filter(pk=item_type_id).select_related('item_category').first()
    if not item_type:
        errors.append('Select a valid item type.')

    if edit_pk:
        try:
            sid = int(body.get('stk_adj_id'))
        except (TypeError, ValueError):
            sid = 0
        if sid != edit_pk:
            errors.append('Missing or invalid document id for edit.')

    if not isinstance(lines_in, list) or len(lines_in) == 0:
        errors.append('Add at least one product or item line.')

    if errors:
        return (errors, None)

    assert d is not None and item_type is not None

    keys_seen: set[tuple[str, int]] = set()
    lines_out: list[dict[str, Any]] = []

    for idx, row in enumerate(lines_in):
        prefix = f'Line {idx + 1}:'
        if not isinstance(row, dict):
            errors.append(f'{prefix} invalid row.')
            continue
        kind = (row.get('kind') or '').strip().upper()
        if kind not in ('P', 'I'):
            errors.append(f'{prefix} missing line kind.')
            continue
        try:
            mid = int(row.get('master_id'))
        except (TypeError, ValueError):
            errors.append(f'{prefix} missing product or item.')
            continue

        rk = (kind, mid)
        if rk in keys_seen:
            errors.append(f'{prefix} duplicate product or item.')
        keys_seen.add(rk)

        line_remarks = (row.get('remarks') or '').strip()
        if len(line_remarks) > 20:
            errors.append(f'{prefix} remarks must be at most 20 characters.')

        batches_in = row.get('batches')
        if not isinstance(batches_in, list) or len(batches_in) == 0:
            errors.append(f'{prefix} add at least one batch line.')
            continue

        prod_obj: MstProd | None = None
        item_obj: MstItem | None = None
        if kind == 'P':
            prod_obj = MstProd.objects.filter(pk=mid).select_related('prod_category').first()
            if not prod_obj:
                errors.append(f'{prefix} invalid product.')
                continue
            if prod_obj.prod_type_id != item_type.pk:
                errors.append(f'{prefix} product does not match the selected item type.')
                continue
            if not MstCustProd.objects.filter(customer_id=customer_id, product_id=mid).exists():
                errors.append(f'{prefix} product is not linked to this customer.')
                continue
        else:
            item_obj = MstItem.objects.filter(pk=mid).select_related('item_category').first()
            if not item_obj:
                errors.append(f'{prefix} invalid item.')
                continue
            if item_obj.item_type_id != item_type.pk:
                errors.append(f'{prefix} item does not match the selected item type.')
                continue

        batches_out: list[dict[str, Any]] | None = []
        line_total = Decimal('0')
        seen_batch_no: set[str] = set()

        for j, b in enumerate(batches_in):
            bp = f'{prefix} batch {j + 1}:'
            if not isinstance(b, dict):
                errors.append(f'{bp} invalid.')
                batches_out = None
                break
            bno = (b.get('batch_no') or '').strip()
            if bno in seen_batch_no:
                errors.append(f'{bp} duplicate batch number in this line.')
                batches_out = None
                break
            seen_batch_no.add(bno)
            mfg_raw = b.get('mfg_date')
            exp_raw = b.get('exp_date')
            mfg = parse_date(str(mfg_raw).strip()) if mfg_raw else None
            exp = parse_date(str(exp_raw).strip()) if exp_raw else None

            if kind == 'I' and item_obj:
                if item_obj.mfg_date != 'Y':
                    mfg = None
                if item_obj.exp_date != 'Y':
                    exp = None

            try:
                bqty = _q(b.get('batch_qty'))
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f'{bp} invalid quantity.')
                batches_out = None
                break

            if bqty == 0:
                errors.append(f'{bp} quantity cannot be zero.')
                batches_out = None
                break

            if stk_adj_type == TrnStkAdjHed.TYPE_OPENING and bqty < 0:
                errors.append(f'{bp} opening balance cannot be negative.')
                batches_out = None
                break

            if kind == 'P' and not bno:
                errors.append(f'{bp} batch number is required for products.')
                batches_out = None
                break

            if kind == 'I' and item_obj and item_obj.maintain_batch == 'Y' and not bno:
                errors.append(f'{bp} batch number is required for this item.')
                batches_out = None
                break

            if mfg and exp and exp < mfg:
                errors.append(f'{bp} expiry date cannot be before manufacturing date.')
                batches_out = None
                break

            assert batches_out is not None
            batches_out.append(
                {
                    'batch_no': bno,
                    'mfg_date': mfg,
                    'exp_date': exp,
                    'batch_qty': bqty,
                }
            )
            line_total += bqty

        if batches_out is None:
            continue

        if line_total == 0:
            errors.append(f'{prefix} total quantity cannot be zero.')
            continue

        lines_out.append(
            {
                'kind': kind,
                'master_id': mid,
                'remarks': line_remarks[:20],
                'batches': batches_out,
            }
        )

    if errors:
        return (errors, None)

    if stk_adj_type == TrnStkAdjHed.TYPE_ADJUST:
        agg: dict[tuple[str, int, str], Decimal] = defaultdict(Decimal)
        for row in lines_out:
            kind = row['kind']
            mid = int(row['master_id'])
            for b in row['batches']:
                key = (kind, mid, (b['batch_no'] or '').strip())
                agg[key] += _q(b['batch_qty'])

        for (kind, mid, bno), delta in agg.items():
            flt: dict[str, Any] = {'customer_id': customer_id, 'batch_no': bno}
            if kind == 'P':
                flt['product_id'] = mid
                flt['item_id'] = None
            else:
                flt['item_id'] = mid
                flt['product_id'] = None
            inv = InventoryStock.objects.filter(**flt, is_closed=False).first()
            label = f'product id {mid}' if kind == 'P' else f'item id {mid}'
            if not inv:
                errors.append(
                    f'Stock adjustment: no existing inventory for {label}, batch {bno!r}. '
                    'Use opening balance or an inward GRN to create this batch first.'
                )
                continue
            if _q(inv.qty + delta) < 0:
                errors.append(
                    f'Stock adjustment: result would be negative for {label}, batch {bno!r} '
                    f'(current {_q(inv.qty)}, change {_q(delta)}).'
                )

    if errors:
        return (errors, None)

    return (
        [],
        {
            'header_pk': edit_pk if edit_pk else None,
            'customer_id': customer_id,
            'stk_adj_dt': d,
            'stk_adj_type': stk_adj_type,
            'item_type_id': item_type_id,
            'remarks': remarks,
            'lines': lines_out,
        },
    )
