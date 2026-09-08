"""
Inward (GRN) — Raw Material Register (full, with QC columns) and
Inward register (standard) — operational line layout.

Data: TrnInwHed, TrnInwDtl1, TrnInwDtl2. Quantity received on the full register
uses batch line ``batch_qty`` from the database with ``pack_style`` as description
(not parsed as a quantity).
"""

from __future__ import annotations

from calendar import month_abbr
from datetime import date
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Prefetch

from masters.models import MstProdCat
from transactions.constants import GRN_CATEGORY_IDS
from transactions.models import TrnInwDtl1, TrnInwDtl2, TrnInwHed

SLUG_FULL = 'inward_rm_register_full'
LABEL_FULL = 'Inward — Raw Material Register (with A.R. No.)'
DESCRIPTION_FULL = (
    'Physical-register style listing per GRN line / batch. Includes P.T.L., '
    'A. R. No., and date-of-report columns (populate when available in data).'
)

SLUG_STANDARD = 'inward_rm_register_standard'
LABEL_STANDARD = 'Inward — Raw Material Register (standard)'
DESCRIPTION_STANDARD = (
    'Line-wise inward listing: party, dates, GRN, supplier, goods, packing, '
    'qty, UOM, pkg_style, rate, batch, linked product, and transporter.'
)

_COL_DEFS_FULL = [
    {'key': 'reg_no_date', 'label': 'Reg. No. / Date', 'default': True},
    {'key': 'grn_no', 'label': 'G.R.N. No.', 'default': True},
    {'key': 'raw_material', 'label': 'Name of Raw Material', 'default': True},
    {'key': 'batch_no', 'label': 'Batch No.', 'default': True},
    {'key': 'mfg_exp', 'label': 'Mfg. Date / Exp. Date', 'default': True},
    {'key': 'order_no_date', 'label': 'Order No. / Date', 'default': True},
    {'key': 'challan_no_date', 'label': 'Challan No. / Date', 'default': True},
    {'key': 'qty_received', 'label': 'Quantity Received', 'default': True},
    {'key': 'qty_sampled', 'label': 'Quantity Sampled', 'default': True},
    {'key': 'mfg_supplier', 'label': 'Manufacturer / Supplier', 'default': True},
    {'key': 'party_name', 'label': 'Party Name', 'default': True},
    {'key': 'ptl_no', 'label': 'P. T. L. No.', 'default': True},
    {'key': 'ar_no', 'label': 'A. R. No.', 'default': True},
    {'key': 'report_dt', 'label': 'Date of Report', 'default': True},
]

_COL_DEFS_STANDARD = [
    {'key': 'party_short', 'label': 'Party name', 'default': True},
    {'key': 'received_date', 'label': 'Received date', 'default': True},
    {'key': 'grn_type', 'label': 'GRN type', 'default': True},
    {'key': 'grn_no', 'label': 'GRN no.', 'default': True},
    {'key': 'challan_invoice', 'label': 'Challan / invoice date', 'default': True},
    {'key': 'supplier_name', 'label': 'Name of supplier', 'default': True},
    {'key': 'goods_description', 'label': 'Description of goods', 'default': True},
    {'key': 'packing', 'label': 'Packing', 'default': True},
    {'key': 'quantity', 'label': 'Quantity', 'default': True},
    {'key': 'uom', 'label': 'Units (UOM)', 'default': True},
    {'key': 'pkg_style', 'lable': 'Packing Style', 'default': True},
    {'key': 'rate', 'label': 'Rate', 'default': True},
    {'key': 'batch_no', 'label': 'Batch no.', 'default': True},
    {'key': 'product_name', 'label': 'Product name', 'default': True},
    {'key': 'transporter_name', 'label': 'Transporter name', 'default': True},
]

_DEFAULT_KEYS_FULL = [c['key'] for c in _COL_DEFS_FULL]
_DEFAULT_KEYS_STANDARD = [c['key'] for c in _COL_DEFS_STANDARD]


def _fmt_dd_mm_yy(d: date | None) -> str:
    if not d:
        return ''
    return d.strftime('%d.%m.%y')


def _fmt_mon_yy(d: date | None) -> str:
    if not d:
        return ''
    abbr = month_abbr[d.month]
    return f'{abbr}-{d.strftime("%y")}'


def _fmt_mfg_exp(mfg: date | None, exp: date | None) -> str:
    a = _fmt_mon_yy(mfg)
    b = _fmt_mon_yy(exp)
    if a and b:
        return f'{a} / {b}'
    return a or b or ''


def _fmt_qty_val(qty) -> str:
    """
    Human-readable quantity string. Do not use ``str.rstrip('0')`` on the whole
    value — e.g. ``'10'.rstrip('0')`` becomes ``'1'``.
    """
    if qty is None:
        return ''
    d = qty if isinstance(qty, Decimal) else Decimal(str(qty))
    s = format(d.normalize(), 'f')
    if '.' not in s:
        return s
    return s.rstrip('0').rstrip('.')


def _qty_received_display(*, d1: TrnInwDtl1, batch: TrnInwDtl2 | None) -> str:
    """
    Packing style (free text) plus the actual received quantity from the batch
    line (``batch_qty``), never inferred from pack_style text.
    """
    uom = d1.uom.short_name if d1.uom_id else ''
    if batch is not None:
        qty_s = _fmt_qty_val(batch.batch_qty)
        ps = (batch.pack_style or '').strip()
        if ps:
            return f'{ps} — {qty_s} {uom}'.strip()
        return f'{qty_s} {uom}'.strip() if qty_s else ''
    return f'{_fmt_qty_val(d1.quantity)} {uom}'.strip()


def _party_short_display(hed: TrnInwHed) -> str:
    if not hed.customer_id:
        return ''
    return (hed.customer.short_name or '').strip()


def filter_options_grn_category():
    qs = (
        MstProdCat.objects.filter(prod_cat_id__in=list(GRN_CATEGORY_IDS))
        .order_by('prod_cat_name')
        .values('prod_cat_id', 'prod_cat_name')
    )
    return [{'id': r['prod_cat_id'], 'label': r['prod_cat_name']} for r in qs]


def _hed_queryset(filters: dict) -> list[TrnInwHed]:
    qs = TrnInwHed.objects.select_related(
        'customer', 'supplier', 'grn_category', 'transporter'
    ).prefetch_related(
        Prefetch(
            'lines',
            queryset=TrnInwDtl1.objects.select_related('item', 'item__item_type', 'uom'),
        ),
        Prefetch(
            'batch_lines',
            queryset=TrnInwDtl2.objects.select_related('item', 'product'),
        ),
    )

    dr = filters.get('inward_period') or {}
    if isinstance(dr, dict):
        d_from = (dr.get('from') or '').strip()
        d_to = (dr.get('to') or '').strip()
        if d_from:
            qs = qs.filter(inward_dt__gte=d_from)
        if d_to:
            qs = qs.filter(inward_dt__lte=d_to)

    gc = filters.get('grn_category') or {}
    if gc.get('mode') == 'select':
        ids = [str(x).strip() for x in (gc.get('ids') or []) if str(x).strip()]
        if ids:
            qs = qs.filter(grn_category_id__in=ids)

    return list(qs.order_by('-inward_dt', '-inward_id'))


def _expand_rows(heds: list[TrnInwHed]) -> list[tuple[TrnInwHed, TrnInwDtl1, TrnInwDtl2 | None]]:
    out: list[tuple[TrnInwHed, TrnInwDtl1, TrnInwDtl2 | None]] = []
    for hed in heds:
        lines = list(hed.lines.all())
        batches = list(hed.batch_lines.all())
        for d1 in lines:
            item = d1.item
            if getattr(item, 'maintain_batch', None) == 'Y':
                item_batches = [b for b in batches if b.item_id == d1.item_id]
                if not item_batches:
                    out.append((hed, d1, None))
                else:
                    for b in sorted(item_batches, key=lambda x: x.batch_no or ''):
                        out.append((hed, d1, b))
            else:
                out.append((hed, d1, None))
    return out


def _serialize_row_full(
    hed: TrnInwHed,
    d1: TrnInwDtl1,
    batch: TrnInwDtl2 | None,
    columns: list[str],
) -> dict:
    item = d1.item
    row: dict = {}
    if 'reg_no_date' in columns:
        row['reg_no_date'] = f"{hed.register_no} / {_fmt_dd_mm_yy(hed.inward_dt)}".strip()
    if 'grn_no' in columns:
        row['grn_no'] = hed.grn_no or ''
    if 'raw_material' in columns:
        row['raw_material'] = item.item_name if item else ''
    if 'batch_no' in columns:
        row['batch_no'] = (batch.batch_no if batch else '') or ''
    if 'mfg_exp' in columns:
        if batch:
            row['mfg_exp'] = _fmt_mfg_exp(batch.mfg_dt, batch.exp_dt)
        else:
            row['mfg_exp'] = ''
    if 'order_no_date' in columns:
        row['order_no_date'] = ''
    if 'challan_no_date' in columns:
        inv = hed.inv_no or ''
        invd = _fmt_dd_mm_yy(hed.inv_dt) if hed.inv_dt else ''
        row['challan_no_date'] = f'{inv} / {invd}'.strip(' /') if (inv or invd) else ''
    if 'qty_received' in columns:
        row['qty_received'] = _qty_received_display(d1=d1, batch=batch)
    if 'qty_sampled' in columns:
        row['qty_sampled'] = ''
    if 'mfg_supplier' in columns:
        row['mfg_supplier'] = hed.supplier.supl_name if hed.supplier_id else ''
    if 'party_name' in columns:
        row['party_name'] = _party_short_display(hed)
    if 'ptl_no' in columns:
        row['ptl_no'] = ''
    if 'ar_no' in columns:
        row['ar_no'] = (batch.arn_no or '').strip() if batch else ''
    if 'report_dt' in columns:
        row['report_dt'] = ''
    return row


def _serialize_row_standard(
    hed: TrnInwHed,
    d1: TrnInwDtl1,
    batch: TrnInwDtl2 | None,
    columns: list[str],
) -> dict:
    item = d1.item
    row: dict = {}
    if 'party_short' in columns:
        row['party_short'] = _party_short_display(hed)
    if 'received_date' in columns:
        row['received_date'] = _fmt_dd_mm_yy(hed.inward_dt)
    if 'grn_type' in columns:
        row['grn_type'] = (
            hed.grn_category.prod_cat_name if hed.grn_category_id else str(hed.grn_category_id or '')
        )
    if 'grn_no' in columns:
        row['grn_no'] = hed.grn_no or ''
    if 'challan_invoice' in columns:
        inv = hed.inv_no or ''
        invd = _fmt_dd_mm_yy(hed.inv_dt) if hed.inv_dt else ''
        row['challan_invoice'] = f'{inv} / {invd}'.strip(' /') if (inv or invd) else ''
    if 'supplier_name' in columns:
        row['supplier_name'] = hed.supplier.supl_name if hed.supplier_id else ''
    if 'goods_description' in columns:
        row['goods_description'] = item.item_name if item else ''
    if 'packing' in columns:
        row['packing'] = (batch.pack_style if batch else '') or ''
    if 'quantity' in columns:
        if batch is not None:
            row['quantity'] = _fmt_qty_val(batch.batch_qty)
        else:
            row['quantity'] = _fmt_qty_val(d1.quantity)
    if 'uom' in columns:
        row['uom'] = d1.uom.short_name if d1.uom_id else ''
    if 'pkg_style' in columns:
        row['pkg_style'] = d1.pkg_style
    if 'rate' in columns:
        if item and item.last_purchase_rate is not None:
            row['rate'] = _fmt_rate(item.last_purchase_rate)
        else:
            row['rate'] = ''
    if 'batch_no' in columns:
        row['batch_no'] = (batch.batch_no if batch else '') or ''
    if 'product_name' in columns:
        if batch and batch.product_id and batch.product:
            row['product_name'] = batch.product.prod_name
        else:
            row['product_name'] = ''
    if 'transporter_name' in columns:
        row['transporter_name'] = (
            hed.transporter.transport_name if hed.transporter_id else ''
        )
    return row


def _fmt_rate(val) -> str:
    if val is None:
        return ''
    d = val if isinstance(val, Decimal) else Decimal(str(val))
    return format(d.quantize(Decimal('0.01')), 'f')


def _column_defs(keys: list[str], *, variant: str) -> list[dict]:
    meta = _COL_DEFS_STANDARD if variant == 'standard' else _COL_DEFS_FULL
    labels = {c['key']: c['label'] for c in meta}
    defs = [{'key': 'sr', 'label': 'Sr. No.'}]
    for k in keys:
        if k == 'sr':
            continue
        defs.append({'key': k, 'label': labels.get(k, k)})
    return defs


def _run(payload: dict, *, variant: str) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}

    is_standard = variant == 'standard'
    default_keys = _DEFAULT_KEYS_STANDARD if is_standard else _DEFAULT_KEYS_FULL
    columns = payload.get('columns')
    if not isinstance(columns, list) or not columns:
        columns = list(default_keys)
    columns = [c for c in columns if c in default_keys]

    export_mode = bool(payload.get('export'))
    page = max(1, int(payload.get('page') or 1))
    per_page = min(100, max(5, int(payload.get('per_page') or 25)))

    heds = _hed_queryset(filters)
    flat = _expand_rows(heds)

    rows_full: list[dict] = []
    for hed, d1, batch in flat:
        if is_standard:
            r = _serialize_row_standard(hed, d1, batch, default_keys)
        else:
            r = _serialize_row_full(hed, d1, batch, default_keys)
        rows_full.append(r)

    rows_slim: list[dict] = []
    for r in rows_full:
        slim = {k: r.get(k, '') for k in columns}
        rows_slim.append(slim)

    col_defs = _column_defs(['sr'] + columns, variant=variant)

    if export_mode:
        rows_out = []
        for idx, row in enumerate(rows_slim, start=1):
            rows_out.append({'sr': idx, **row})
        return {
            'layout': 'tabular',
            'group_by': 'none',
            'columns': col_defs,
            'rows': rows_out,
            'total_count': len(rows_out),
            'page': 1,
            'per_page': len(rows_out),
            'total_pages': 1,
        }

    paginator = Paginator(rows_slim, per_page)
    pg = paginator.get_page(page)
    start = (pg.number - 1) * per_page
    paged = []
    for i, row in enumerate(pg.object_list, start=start + 1):
        paged.append({'sr': i, **row})

    return {
        'layout': 'tabular',
        'group_by': 'none',
        'columns': col_defs,
        'rows': paged,
        'total_count': paginator.count,
        'page': pg.number,
        'per_page': per_page,
        'total_pages': paginator.num_pages,
    }


def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
    return result.get('columns') or [], result.get('rows') or []


_SHARED_FILTERS = [
    {
        'key': 'inward_period',
        'label': 'Inward date',
        'kind': 'date_range',
    },
    {
        'key': 'grn_category',
        'label': 'GRN type (RM / PM)',
        'kind': 'all_or_multiselect',
        'list_label': 'Select types',
    },
]


class InwardRmRegisterFull:
    SLUG = SLUG_FULL
    LABEL = LABEL_FULL
    DESCRIPTION = DESCRIPTION_FULL

    @staticmethod
    def get_ui_config() -> dict:
        return {
            'slug': SLUG_FULL,
            'label': LABEL_FULL,
            'print_title': 'Raw Material Register',
            'description': DESCRIPTION_FULL,
            'layout': 'tabular',
            'group_by_options': [{'value': 'none', 'label': 'Flat list'}],
            'default_group_by': 'none',
            'filters': list(_SHARED_FILTERS),
            'columns': list(_COL_DEFS_FULL),
            'default_columns': list(_DEFAULT_KEYS_FULL),
            'sortable': [],
            'default_sort': {},
        }

    @staticmethod
    def run(payload: dict) -> dict:
        return _run(payload, variant='full')

    @staticmethod
    def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
        return flatten_for_export(result)


class InwardRmRegisterStandard:
    SLUG = SLUG_STANDARD
    LABEL = LABEL_STANDARD
    DESCRIPTION = DESCRIPTION_STANDARD

    @staticmethod
    def get_ui_config() -> dict:
        return {
            'slug': SLUG_STANDARD,
            'label': LABEL_STANDARD,
            'print_title': 'Inward register',
            'description': DESCRIPTION_STANDARD,
            'layout': 'tabular',
            'group_by_options': [{'value': 'none', 'label': 'Flat list'}],
            'default_group_by': 'none',
            'filters': list(_SHARED_FILTERS),
            'columns': list(_COL_DEFS_STANDARD),
            'default_columns': list(_DEFAULT_KEYS_STANDARD),
            'sortable': [],
            'default_sort': {},
        }

    @staticmethod
    def run(payload: dict) -> dict:
        return _run(payload, variant='standard')

    @staticmethod
    def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
        return flatten_for_export(result)
