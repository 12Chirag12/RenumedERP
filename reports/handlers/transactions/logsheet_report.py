"""
Log sheet register — optional granulation date range; flat or customer-wise layout.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.utils.dateparse import parse_date

from masters.models import MstProd
from transactions.models import (
    LOGSHEET_LAYER_SLOT_FIRST,
    LOGSHEET_LAYER_SLOT_SECOND,
    TrnLogSheet,
    logsheet_split_batch_qty,
)

SLUG = 'log_sheet_register'
LABEL = 'Log sheet register'
DESCRIPTION = (
    'Granulation log sheets. Dates are optional (omit both to list up to the row cap). '
    'Choose a flat list or customer-wise blocks. Columns match the standard log sheet layout.'
)

_COL_DEFS = [
    {'key': 'shift', 'label': 'Shift', 'default': True},
    {'key': 'mc', 'label': 'M/C', 'default': True},
    {'key': 'product_name', 'label': 'Product Name', 'default': True},
    {'key': 'batch_no', 'label': 'Batch No', 'default': True},
    {'key': 'batch_size', 'label': 'Batch Size', 'default': True},
    {'key': 'mfg_dt', 'label': 'Mfg_dt', 'default': True},
    {'key': 'exp_dt', 'label': 'Exp_dt', 'default': True},
    {'key': 'gran_dt', 'label': 'Granu. Dt', 'default': True},
    {'key': 'blend_dt', 'label': 'Blend Dt', 'default': True},
    {'key': 'compression', 'label': 'Compression', 'default': True},
    {'key': 'coating', 'label': 'Coating', 'default': True},
    {'key': 'party', 'label': 'Party', 'default': True},
]

_DEFAULT_KEYS = [c['key'] for c in _COL_DEFS]
_MAX_RANGE_DAYS = 366
_MAX_ROWS = 5000


def _batch_size_display(qty_l, qty_n) -> str:
    """Same convention as DPR / batch allocation (lac + nos)."""
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


def _batch_size_for_row(ls: TrnLogSheet, bl) -> str:
    if not bl:
        return ''
    prod = ls.product
    layer = (prod.tablet_layer if prod else None) or MstProd.LAYER_SINGLE
    if layer == MstProd.LAYER_DOUBLE and ls.layer_slot in (
        LOGSHEET_LAYER_SLOT_FIRST,
        LOGSHEET_LAYER_SLOT_SECOND,
    ):
        n1, n2, l1, l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l)
        if ls.layer_slot == LOGSHEET_LAYER_SLOT_FIRST:
            return _batch_size_display(l1, n1)
        return _batch_size_display(l2, n2)
    return _batch_size_display(bl.batch_qty_l, bl.batch_qty_n)


def _fmt_dd_mm_yyyy(d: date | None) -> str:
    if not d:
        return ''
    return d.strftime('%d-%m-%Y')


def _serialize(ls: TrnLogSheet, columns: list[str]) -> dict:
    bl = ls.batch_line
    row: dict = {}
    if 'shift' in columns:
        row['shift'] = (ls.shift_id or '').strip()
    if 'mc' in columns:
        row['mc'] = ls.section.section_name if ls.section_id else ''
    if 'product_name' in columns:
        row['product_name'] = ls.product.prod_name if ls.product_id else ''
    if 'batch_no' in columns:
        row['batch_no'] = bl.batch_no if bl else ''
    if 'batch_size' in columns:
        row['batch_size'] = _batch_size_for_row(ls, bl)
    if 'mfg_dt' in columns:
        row['mfg_dt'] = (bl.mfg_dt or '') if bl else ''
    if 'exp_dt' in columns:
        row['exp_dt'] = (bl.exp_dt or '') if bl else ''
    if 'gran_dt' in columns:
        row['gran_dt'] = _fmt_dd_mm_yyyy(ls.gran_dt)
    if 'blend_dt' in columns:
        row['blend_dt'] = _fmt_dd_mm_yyyy(ls.blend_dt) if ls.blend_dt else ''
    if 'compression' in columns:
        row['compression'] = ''
    if 'coating' in columns:
        row['coating'] = ''
    if 'party' in columns:
        c = ls.customer
        row['party'] = (c.short_name or '').strip() or (c.cust_name or '') if ls.customer_id else ''
    return row


def _column_defs(keys: list[str]) -> list[dict]:
    labels = {c['key']: c['label'] for c in _COL_DEFS}
    defs = [{'key': 'sr', 'label': 'Sr. No.'}]
    for k in keys:
        if k == 'sr':
            continue
        defs.append({'key': k, 'label': labels.get(k, k)})
    return defs


def _optional_gran_period(filters: dict) -> tuple[date | None, date | None]:
    """Both dates optional; empty means no granulation date filter (still capped at _MAX_ROWS)."""
    dr = filters.get('gran_period') or {}
    if not isinstance(dr, dict):
        dr = {}
    raw_from = (dr.get('from') or '').strip()
    raw_to = (dr.get('to') or '').strip()
    if not raw_from and not raw_to:
        return None, None
    d_from = parse_date(raw_from) if raw_from else None
    d_to = parse_date(raw_to) if raw_to else None
    if raw_from and not d_from:
        raise ValueError('Invalid granulation start date.')
    if raw_to and not d_to:
        raise ValueError('Invalid granulation end date.')
    if d_from and d_to:
        if d_to < d_from:
            raise ValueError('End date must be on or after start date.')
        if (d_to - d_from).days > _MAX_RANGE_DAYS:
            raise ValueError(f'Date range must not exceed {_MAX_RANGE_DAYS} days.')
    return d_from, d_to


def _report_subtitle(d_from: date | None, d_to: date | None) -> str:
    if d_from and d_to:
        return f'LogSheet From {_fmt_dd_mm_yyyy(d_from)} To {_fmt_dd_mm_yyyy(d_to)}'
    if d_from:
        return f'LogSheet From {_fmt_dd_mm_yyyy(d_from)} onwards'
    if d_to:
        return f'LogSheet up to {_fmt_dd_mm_yyyy(d_to)}'
    return f'LogSheet (all dates; up to {_MAX_ROWS:,} rows)'


def _read_group_by(payload: dict) -> str:
    raw = payload.get('group_by')
    if isinstance(raw, str) and raw.strip().lower() in ('none', 'customer'):
        return raw.strip().lower()
    return 'customer'


def run(payload: dict) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}

    d_from, d_to = _optional_gran_period(filters)
    group_by = _read_group_by(payload)

    columns = payload.get('columns')
    if not isinstance(columns, list) or not columns:
        columns = list(_DEFAULT_KEYS)
    columns = [c for c in columns if c in _DEFAULT_KEYS]

    export_mode = bool(payload.get('export'))
    subtitle = _report_subtitle(d_from, d_to)

    qs = TrnLogSheet.objects.select_related('section', 'product', 'batch_line', 'customer')
    if d_from and d_to:
        qs = qs.filter(gran_dt__range=(d_from, d_to))
    elif d_from:
        qs = qs.filter(gran_dt__gte=d_from)
    elif d_to:
        qs = qs.filter(gran_dt__lte=d_to)

    if group_by == 'customer':
        qs = qs.order_by('customer__cust_name', '-gran_dt', '-logsheet_id')
    else:
        qs = qs.order_by('-gran_dt', '-logsheet_id')

    items = list(qs[:_MAX_ROWS])
    col_defs = _column_defs(['sr'] + columns)

    if group_by == 'none':
        rows_slim = [_serialize(ls, columns) for ls in items]
        if export_mode:
            rows_out = [{'sr': i, **r} for i, r in enumerate(rows_slim, start=1)]
            return {
                'layout': 'tabular',
                'group_by': 'none',
                'columns': col_defs,
                'rows': rows_out,
                'total_count': len(rows_out),
                'page': 1,
                'per_page': len(rows_out),
                'total_pages': 1,
                'meta': {'report_subtitle': subtitle},
            }
        page = max(1, int(payload.get('page') or 1))
        per_page = min(100, max(5, int(payload.get('per_page') or 25)))
        paginator = Paginator(rows_slim, per_page)
        pg = paginator.get_page(page)
        start = (pg.number - 1) * per_page
        paged = [{'sr': i, **row} for i, row in enumerate(pg.object_list, start=start + 1)]
        return {
            'layout': 'tabular',
            'group_by': 'none',
            'columns': col_defs,
            'rows': paged,
            'total_count': paginator.count,
            'page': pg.number,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
            'meta': {'report_subtitle': subtitle},
        }

    group_page = max(1, int(payload.get('group_page') or 1))
    group_per_page = min(50, max(1, int(payload.get('group_per_page') or 10)))

    buckets: dict[int, list[TrnLogSheet]] = defaultdict(list)
    ordered_cust_ids: list[int] = []
    seen: set[int] = set()
    for ls in items:
        buckets[ls.customer_id].append(ls)
        if ls.customer_id not in seen:
            seen.add(ls.customer_id)
            ordered_cust_ids.append(ls.customer_id)

    total_groups = len(ordered_cust_ids)
    if export_mode:
        slice_ids = ordered_cust_ids
    else:
        start_g = (group_page - 1) * group_per_page
        slice_ids = ordered_cust_ids[start_g : start_g + group_per_page]

    groups: list[dict] = []
    for cid in slice_ids:
        rows_src = buckets[cid]
        if not rows_src:
            continue
        cust = rows_src[0].customer
        header = (cust.short_name or '').strip() or (cust.cust_name or '')
        inner: list[dict] = []
        for idx, ls in enumerate(rows_src, start=1):
            r = _serialize(ls, columns)
            r['sr'] = idx
            inner.append(r)
        groups.append({'header': header, 'rows': inner})

    total_group_pages = max(1, math.ceil(total_groups / group_per_page)) if total_groups else 1

    return {
        'layout': 'grouped',
        'group_by': 'customer',
        'columns': col_defs,
        'groups': groups,
        'total_count': len(items),
        'total_groups': total_groups,
        'group_page': group_page if not export_mode else 1,
        'group_per_page': group_per_page if not export_mode else total_groups or 1,
        'total_group_pages': total_group_pages,
        'meta': {'report_subtitle': subtitle},
    }


def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
    cols = result.get('columns') or []
    if result.get('layout') == 'grouped':
        exp_cols = [{'key': '__section__', 'label': 'Party (group)'}] + cols
        keys = [c['key'] for c in exp_cols]
        rows: list[dict] = []
        for g in result.get('groups') or []:
            blank = {k: '' for k in keys}
            blank['__section__'] = g.get('header', '')
            rows.append(blank)
            for r in g.get('rows') or []:
                row = {k: '' for k in keys}
                row.update(r)
                rows.append(row)
        return exp_cols, rows
    return cols, result.get('rows') or []


class LogSheetRegisterReport:
    SLUG = SLUG
    LABEL = LABEL
    DESCRIPTION = DESCRIPTION

    @staticmethod
    def get_ui_config() -> dict:
        return {
            'slug': SLUG,
            'label': LABEL,
            'print_title': 'Logsheet',
            'description': DESCRIPTION,
            'group_by_options': [
                {'value': 'none', 'label': 'Flat list'},
                {'value': 'customer', 'label': 'Customer-wise list'},
            ],
            'default_group_by': 'customer',
            'filters': [
                {
                    'key': 'gran_period',
                    'label': 'Granulation date (optional)',
                    'kind': 'date_range',
                    'placeholder_from': 'From',
                    'placeholder_to': 'To',
                },
            ],
            'columns': list(_COL_DEFS),
            'default_columns': list(_DEFAULT_KEYS),
            'sortable': [],
            'default_sort': {},
        }

    @staticmethod
    def run(payload: dict) -> dict:
        return run(payload)

    @staticmethod
    def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
        return flatten_for_export(result)
