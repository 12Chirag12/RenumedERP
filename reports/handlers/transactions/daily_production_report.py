"""
Daily production report (DPR) — single date, section blocks with totals, shift filter.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import Prefetch
from django.utils.dateparse import parse_date

from masters.models import MstProd, MstSection
from transactions.models import (
    DPR_MACHINE_NOT_WORKING,
    DPR_MACHINE_WORKING,
    LOGSHEET_LAYER_SLOT_FIRST,
    LOGSHEET_LAYER_SLOT_SECOND,
    LOGSHEET_LAYER_SLOT_SINGLE,
    LOGSHEET_SHIFT_DAY,
    LOGSHEET_SHIFT_NIGHT,
    TrnDpr,
    TrnDprInputBatch,
    TrnLogSheet,
    logsheet_split_batch_qty,
)

SLUG = 'daily_production_report'
LABEL = 'Daily production report'
DESCRIPTION = (
    'DPR for one calendar day: grouped by section and machine with a banner row, '
    'detail lines, and per-block totals. Filter by sections and shift (Day / Night / Day+Night).'
)

_COL_DEFS = [
    {'key': 'date', 'label': 'Date', 'default': True},
    {'key': 'section', 'label': 'Section', 'default': True},
    {'key': 'product_name', 'label': 'Product name', 'default': True},
    {'key': 'batch_no', 'label': 'Batch no.', 'default': True},
    {'key': 'qty_kg', 'label': 'Qty in kg', 'default': True},
    {'key': 'qty_nos', 'label': 'No. of tablets', 'default': True},
    {'key': 'unit', 'label': 'Unit', 'default': True},
    {'key': 'start_time', 'label': 'Start time', 'default': True},
    {'key': 'end_time', 'label': 'End time', 'default': True},
    {'key': 'total_time', 'label': 'Total', 'default': True},
    {'key': 'operator', 'label': 'Operator', 'default': True},
    {'key': 'helpers', 'label': 'No. of helpers', 'default': True},
]

_DEFAULT_KEYS = [c['key'] for c in _COL_DEFS]
_MAX_ROWS = 5000


def filter_options_dpr_section() -> list[dict[str, Any]]:
    rows = MstSection.objects.select_related('department').order_by(
        'department__dept_name', 'section_name'
    )
    return [{'id': s.section_id, 'label': s.section_name} for s in rows]


def _logsheet_batch_caption(ls: TrnLogSheet) -> str:
    """Batch no. + slot label (aligned with DPR entry screen)."""
    bl = ls.batch_line
    if not bl:
        return ''
    prod = ls.product
    layer = (prod.tablet_layer if prod else None) or MstProd.LAYER_SINGLE
    c1 = prod.first_color.color_name if prod and prod.first_color else ''
    c2 = prod.second_color.color_name if prod and prod.second_color else ''
    _n1, _n2, _l1, _l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l)
    if layer == MstProd.LAYER_DOUBLE and ls.layer_slot in (
        LOGSHEET_LAYER_SLOT_FIRST,
        LOGSHEET_LAYER_SLOT_SECOND,
    ):
        if ls.layer_slot == LOGSHEET_LAYER_SLOT_FIRST:
            slot_lbl = f'1st ({c1 or "First colour"})'
        else:
            slot_lbl = f'2nd ({c2 or "Second colour"})'
    else:
        slot_lbl = (
            'Single' if ls.layer_slot == LOGSHEET_LAYER_SLOT_SINGLE else (ls.layer_slot or '—')
        )
    bn = bl.batch_no or ''
    s = (slot_lbl or '').strip()
    if s and s != 'Single':
        return f'{bn} — {slot_lbl}'
    return bn


def _fmt_date_dd_mm_yy(d: date | None) -> str:
    if not d:
        return ''
    return d.strftime('%d-%m-%y')


def _fmt_qty_kg(q) -> str:
    if q in (None, ''):
        return ''
    try:
        d = q if isinstance(q, Decimal) else Decimal(str(q))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        return str(q)
    s = format(d.normalize(), 'f')
    if '.' not in s:
        return s
    return s.rstrip('0').rstrip('.')


def _fmt_qty_nos(n) -> str:
    if n in (None, ''):
        return ''
    try:
        return str(int(n))
    except (TypeError, ValueError):
        return str(n)


def _batch_no_for_row(r: TrnDpr) -> str:
    if r.batch_line_id:
        return (r.batch_line.batch_no or '').strip()
    parts = [
        _logsheet_batch_caption(ib.log_sheet)
        for ib in sorted(r.input_batches.all(), key=lambda x: x.input_id)
        if ib.log_sheet_id
    ]
    joined = ' / '.join(p for p in parts if p)
    return joined if joined else '—'


def _product_display(r: TrnDpr) -> str:
    if r.machine_working == DPR_MACHINE_NOT_WORKING:
        return (r.remarks or '').strip() or 'Machine not working'
    if r.product_id:
        return (r.product.prod_name or '').strip()
    if r.specification_id:
        return (r.specification.spec_name or '').strip()
    return (r.remarks or '').strip()


def _operators_display(r: TrnDpr) -> str:
    parts = []
    if r.operator1_id:
        parts.append((r.operator1.opt_name or '').strip())
    if r.operator2_id:
        parts.append((r.operator2.opt_name or '').strip())
    return ' / '.join(p for p in parts if p)


def _section_machine_label(r: TrnDpr) -> str:
    sn = (r.section.section_name or '').strip() if r.section_id else ''
    mn = (r.machine.machine_name or '').strip() if r.machine_id else ''
    if sn and mn:
        return f'{sn} {{{mn}}}'
    return sn or mn or '—'


def _read_report_date(filters: dict) -> date:
    raw = filters.get('dpr_date')
    if isinstance(raw, str):
        s = raw.strip()
    else:
        s = ''
    if not s:
        raise ValueError('Production date is required.')
    d = parse_date(s)
    if not d:
        raise ValueError('Invalid production date.')
    return d


def _read_shift_filter(filters: dict) -> str:
    block = filters.get('dpr_shift') or {}
    if not isinstance(block, dict):
        return 'day_night'
    v = (block.get('value') or 'day_night').strip().lower()
    if v in ('day', 'night', 'day_night'):
        return v
    return 'day_night'


def _read_section_filter(filters: dict) -> tuple[str, list[int]]:
    block = filters.get('dpr_section') or {}
    if not isinstance(block, dict):
        return 'all', []
    mode = (block.get('mode') or 'all').strip().lower()
    raw_ids = block.get('ids') or []
    ids: list[int] = []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
    return ('select' if mode == 'select' else 'all'), ids


def _serialize_row(r: TrnDpr, report_date: date, section_machine: str, keys: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if 'date' in keys:
        row['date'] = _fmt_date_dd_mm_yy(report_date)
    if 'section' in keys:
        row['section'] = section_machine
    if 'product_name' in keys:
        row['product_name'] = _product_display(r)
    if 'batch_no' in keys:
        row['batch_no'] = _batch_no_for_row(r)
    if 'qty_kg' in keys:
        row['qty_kg'] = _fmt_qty_kg(r.qty_kg) if r.machine_working == DPR_MACHINE_WORKING else ''
    if 'qty_nos' in keys:
        row['qty_nos'] = _fmt_qty_nos(r.qty_nos) if r.machine_working == DPR_MACHINE_WORKING else ''
    if 'unit' in keys:
        u = ''
        if r.product_id and r.product.uom_id:
            u = (r.product.uom.short_name or r.product.uom.uom_name or '').strip()
        row['unit'] = u
    if 'start_time' in keys:
        row['start_time'] = r.start_time.strftime('%H:%M') if r.start_time else ''
    if 'end_time' in keys:
        row['end_time'] = r.end_time.strftime('%H:%M') if r.end_time else ''
    if 'total_time' in keys:
        row['total_time'] = (r.total_time or '').strip()
    if 'operator' in keys:
        row['operator'] = _operators_display(r)
    if 'helpers' in keys:
        row['helpers'] = str(r.no_of_helper) if r.no_of_helper else ''
    return row


def _banner_shift_for_group(rows: list[TrnDpr], shift_filter: str) -> str:
    if shift_filter == 'day':
        return 'Day'
    if shift_filter == 'night':
        return 'Night'
    shifts = {r.shift_id for r in rows}
    if shifts <= {LOGSHEET_SHIFT_DAY}:
        return 'Day'
    if shifts <= {LOGSHEET_SHIFT_NIGHT}:
        return 'Night'
    if LOGSHEET_SHIFT_DAY in shifts and LOGSHEET_SHIFT_NIGHT in shifts:
        return 'Day + Night'
    if len(shifts) == 1:
        return next(iter(shifts))
    return ' / '.join(sorted(shifts))


def _apply_first_row_time_rule(rows: list[dict], keys: list[str]) -> None:
    """Match paper layout: only the first detail row shows time / operator / helpers."""
    time_keys = ('start_time', 'end_time', 'total_time', 'operator', 'helpers')
    for i, row in enumerate(rows):
        if i == 0:
            continue
        for k in time_keys:
            if k in keys:
                row[k] = ''


def _column_defs(keys: list[str]) -> list[dict]:
    labels = {c['key']: c['label'] for c in _COL_DEFS}
    return [{'key': k, 'label': labels.get(k, k)} for k in keys if k in labels]


def _subtitle(report_date: date, shift_filter: str) -> str:
    shift_lbl = {'day': 'Day', 'night': 'Night', 'day_night': 'Day + Night'}.get(shift_filter, shift_filter)
    return f'Daily production report — {_fmt_date_dd_mm_yy(report_date)} ({shift_lbl})'


def run(payload: dict) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}

    report_date = _read_report_date(filters)
    shift_filter = _read_shift_filter(filters)
    sec_mode, sec_ids = _read_section_filter(filters)

    columns = payload.get('columns')
    if not isinstance(columns, list) or not columns:
        columns = list(_DEFAULT_KEYS)
    keys = [c for c in columns if c in _DEFAULT_KEYS]

    qs = (
        TrnDpr.objects.filter(trn_dpr_dt=report_date)
        .select_related(
            'section',
            'machine',
            'customer',
            'product',
            'product__uom',
            'batch_line',
            'operator1',
            'operator2',
            'specification',
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
    )

    if shift_filter == 'day':
        qs = qs.filter(shift_id=LOGSHEET_SHIFT_DAY)
    elif shift_filter == 'night':
        qs = qs.filter(shift_id=LOGSHEET_SHIFT_NIGHT)
    else:
        qs = qs.filter(shift_id__in=[LOGSHEET_SHIFT_DAY, LOGSHEET_SHIFT_NIGHT])

    if sec_mode == 'select' and sec_ids:
        qs = qs.filter(section_id__in=sec_ids)
    elif sec_mode == 'select' and not sec_ids:
        qs = qs.none()

    qs = qs.order_by('section__section_name', 'machine__machine_name', 'start_time', 'trn_dpr_id')[:_MAX_ROWS]
    items = list(qs)

    grouped: dict[tuple[int, int], list[TrnDpr]] = defaultdict(list)
    pair_order: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for r in items:
        key = (r.section_id, r.machine_id)
        grouped[key].append(r)
        if key not in seen:
            seen.add(key)
            pair_order.append(key)

    col_defs = _column_defs(keys)
    groups_out: list[dict[str, Any]] = []

    for key in pair_order:
        bucket = grouped[key]
        if not bucket:
            continue
        first = bucket[0]
        section_machine = _section_machine_label(first)
        banner = _banner_shift_for_group(bucket, shift_filter)

        rows_out: list[dict[str, Any]] = []
        sum_kg = Decimal('0')
        sum_nos = 0
        for r in bucket:
            row = _serialize_row(r, report_date, section_machine, keys)
            rows_out.append(row)
            if r.machine_working == DPR_MACHINE_WORKING:
                try:
                    sum_kg += r.qty_kg if isinstance(r.qty_kg, Decimal) else Decimal(str(r.qty_kg or 0))
                except (InvalidOperation, TypeError, ValueError, ArithmeticError):
                    pass
                try:
                    sum_nos += int(r.qty_nos or 0)
                except (TypeError, ValueError):
                    pass

        _apply_first_row_time_rule(rows_out, keys)

        footer: dict[str, Any] = {k: '' for k in keys}
        if 'product_name' in keys:
            footer['product_name'] = 'TOTAL'
        if 'qty_kg' in keys:
            footer['qty_kg'] = _fmt_qty_kg(sum_kg) if sum_kg else ''
        if 'qty_nos' in keys:
            footer['qty_nos'] = _fmt_qty_nos(sum_nos) if sum_nos else ''

        groups_out.append(
            {
                'section_machine': section_machine,
                'banner_shift': banner,
                'rows': rows_out,
                'footer': footer,
            }
        )

    return {
        'layout': 'dpr_sections',
        'columns': col_defs,
        'groups': groups_out,
        'total_count': len(items),
        'meta': {'report_subtitle': _subtitle(report_date, shift_filter)},
    }


def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
    cols = result.get('columns') or []
    keys = [c['key'] for c in cols]
    flat: list[dict[str, Any]] = []
    for g in result.get('groups') or []:
        banner = {k: '' for k in keys}
        if 'section' in keys:
            banner['section'] = g.get('section_machine') or ''
        if 'product_name' in keys:
            banner['product_name'] = g.get('banner_shift') or ''
        flat.append(banner)
        for r in g.get('rows') or []:
            flat.append({k: r.get(k, '') for k in keys})
        f = g.get('footer') or {}
        flat.append({k: f.get(k, '') for k in keys})
    return cols, flat


class DailyProductionReport:
    SLUG = SLUG
    LABEL = LABEL
    DESCRIPTION = DESCRIPTION

    @staticmethod
    def get_ui_config() -> dict:
        return {
            'slug': SLUG,
            'label': LABEL,
            'print_title': 'Daily production report',
            'description': DESCRIPTION,
            'group_by_options': [],
            'default_group_by': 'none',
            'filters': [
                {
                    'key': 'dpr_date',
                    'label': 'Production date',
                    'kind': 'date_single',
                    'default_today': True,
                },
                {
                    'key': 'dpr_section',
                    'label': 'Section',
                    'kind': 'all_or_multiselect',
                    'list_label': 'Select sections',
                },
                {
                    'key': 'dpr_shift',
                    'label': 'Shift',
                    'kind': 'radio_choice',
                    'input_name': 'tr_dpr_shift',
                    'options': [
                        {'value': 'day_night', 'label': 'Day + Night'},
                        {'value': 'day', 'label': 'Day'},
                        {'value': 'night', 'label': 'Night'},
                    ],
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
