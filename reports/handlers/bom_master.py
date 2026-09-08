"""BOM (RM + PM) report — specification headers or specification-wise grouped detail lines."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

from masters.models import MstBomPmDtl, MstBomPmHed, MstBomRmDtl, MstBomRmHed

SLUG = 'bom_master'
LABEL = 'Bill of Materials (BOM)'
DESCRIPTION = (
    'RM and PM BOM specifications: header list or specification-wise grouped item lines. '
    'Filter by BOM type, customer, and product.'
)

_DEFAULT_COLUMNS = [
    'bom_type',
    'spec_name',
    'customer',
    'product',
    'machine',
    'no_of_lots',
    'batch_size',
    'batch_nos',
    'locked',
    'shape',
    'colour',
    'coating',
    'capsule',
    'avg_wt',
    'pkg_style',
]

# Inner table only (spec name / customer / product are in the group header)
_DEFAULT_BOM_SPEC_GROUP_COLUMNS = [
    'stage_name',
    'item_name',
    'qty',
    'uom',
]

_SORT_KEYS = {
    'bom_type': lambda r: r.get('bom_type') or '',
    'spec_name': lambda r: (r.get('spec_name') or '').lower(),
    'customer': lambda r: (r.get('customer') or '').lower(),
    'product': lambda r: (r.get('product') or '').lower(),
    'batch_size': lambda r: r.get('_batch_sort', 0),
    'locked': lambda r: r.get('_locked_sort', 0),
}

_SORT_KEYS_SPEC_GROUP = {
    'stage_name': lambda r: (r.get('stage_name') or '').lower(),
    'item_name': lambda r: (r.get('item_name') or '').lower(),
    'qty': lambda r: r.get('_qty_sort', Decimal('0')),
    'uom': lambda r: (r.get('uom') or '').lower(),
}


def get_ui_config() -> dict:
    return {
        'slug': SLUG,
        'label': LABEL,
        'description': DESCRIPTION,
        'layout': 'tabular',
        'group_by_options': [{'value': 'none', 'label': 'Flat list'}],
        'default_group_by': 'none',
        'filters': [
            {
                'key': 'bom_row_mode',
                'label': 'View',
                'kind': 'radio_choice',
                'input_name': 'mr_bom_row_mode',
                'radio_layout': 'vertical',
                'options': [
                    {'value': 'headers', 'label': 'Specifications (headers)'},
                    {'value': 'spec_wise_items', 'label': 'Specification-wise item list'},
                ],
            },
            {
                'key': 'bom_kind',
                'label': 'BOM type',
                'kind': 'radio_choice',
                'input_name': 'mr_bom_kind',
                'radio_layout': 'vertical',
                'options': [
                    {'value': 'all', 'label': 'All (RM + PM)'},
                    {'value': 'rm', 'label': 'RM only'},
                    {'value': 'pm', 'label': 'PM only'},
                ],
            },
            {
                'key': 'customer',
                'label': 'Customer',
                'kind': 'all_or_multiselect',
                'list_label': 'Select customers',
            },
            {
                'key': 'product',
                'label': 'Product',
                'kind': 'all_or_multiselect',
                'list_label': 'Select products',
            },
        ],
        'columns': [
            {'key': 'bom_type', 'label': 'BOM type', 'default': True},
            {'key': 'spec_name', 'label': 'Specification', 'default': True},
            {'key': 'customer', 'label': 'Customer', 'default': True},
            {'key': 'product', 'label': 'Product', 'default': True},
            {'key': 'machine', 'label': 'Machine', 'default': True},
            {'key': 'no_of_lots', 'lable': 'No of Lots', 'default': True},
            {'key': 'batch_size', 'label': 'Batch size (lakh)', 'default': True},
            {'key': 'batch_nos', 'label': 'Batch nos.', 'default': True},
            {'key': 'locked', 'label': 'Locked', 'default': True},
            {'key': 'shape', 'label': 'Shape (RM)', 'default': False},
            {'key': 'colour', 'label': 'Colour (RM)', 'default': False},
            {'key': 'coating', 'label': 'Coating (RM)', 'default': False},
            {'key': 'capsule', 'label': 'Capsule (RM)', 'default': False},
            {'key': 'avg_wt', 'label': 'Avg. wt. (RM)', 'default': False},
            {'key': 'pkg_style', 'label': 'Packing style (PM)', 'default': False},
        ],
        'columns_bom_spec_groups': [
            {'key': 'stage_name', 'label': 'Stage', 'default': True},
            {'key': 'item_name', 'label': 'Item', 'default': True},
            {'key': 'qty', 'label': 'Quantity', 'default': True},
            {'key': 'uom', 'label': 'UOM', 'default': True},
        ],
        'default_columns': _DEFAULT_COLUMNS,
        'default_columns_bom_spec_groups': _DEFAULT_BOM_SPEC_GROUP_COLUMNS,
        'sortable': list(_SORT_KEYS.keys()),
        'sortable_bom_spec_groups': list(_SORT_KEYS_SPEC_GROUP.keys()),
        'default_sort': {'column': 'spec_name', 'dir': 'asc'},
        'default_sort_bom_spec_groups': {'column': 'item_name', 'dir': 'asc'},
    }


def _apply_filters_rm(qs, filters: dict):
    cust = filters.get('customer') or {}
    if cust.get('mode') == 'select':
        ids = [int(x) for x in (cust.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(customer_id__in=ids)
    prod = filters.get('product') or {}
    if prod.get('mode') == 'select':
        ids = [int(x) for x in (prod.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(product_id__in=ids)
    return qs


def _bom_kind_scope(filters: dict) -> str:
    bk = filters.get('bom_kind') or {}
    v = str(bk.get('value') or 'all').strip().lower()
    if v == 'rm':
        return 'rm'
    if v == 'pm':
        return 'pm'
    return 'all'


def _bom_row_mode(filters: dict) -> str:
    br = filters.get('bom_row_mode') or {}
    v = str(br.get('value') or 'headers').strip().lower()
    if v == 'spec_wise_items':
        return 'spec_wise_items'
    return 'headers'


def _search_q(s: str) -> Q:
    return (
        Q(spec_name__icontains=s)
        | Q(customer__cust_name__icontains=s)
        | Q(customer__short_name__icontains=s)
        | Q(product__prod_name__icontains=s)
    )


def _search_q_lines(s: str) -> Q:
    return (
        Q(spec__spec_name__icontains=s)
        | Q(spec__customer__cust_name__icontains=s)
        | Q(spec__customer__short_name__icontains=s)
        | Q(spec__product__prod_name__icontains=s)
        | Q(item__item_name__icontains=s)
        | Q(stage__stage_name__icontains=s)
    )


def _row_rm(h: MstBomRmHed, columns: list[str]) -> dict:
    row = {}
    if 'bom_type' in columns:
        row['bom_type'] = 'RM'
    if 'spec_name' in columns:
        row['spec_name'] = h.spec_name
    if 'customer' in columns:
        row['customer'] = f"{h.customer.cust_name} ({h.customer.short_name})"
    if 'product' in columns:
        row['product'] = h.product.prod_name
    if 'machine' in columns:
        row['machine'] = h.machine.machine_name if h.machine_id else ''
    if 'no_of_lots' in columns:
        row['no_of_lots'] = '' if h.no_of_lots is None else str(h.no_of_lots)
    if 'batch_size' in columns:
        row['batch_size'] = str(h.batch_size)
    if 'batch_nos' in columns:
        row['batch_nos'] = str(h.batch_nos)
    if 'locked' in columns:
        row['locked'] = 'Yes' if h.is_locked else 'No'
    if 'shape' in columns:
        row['shape'] = h.shape.shape_name if h.shape_id else ''
    if 'colour' in columns:
        row['colour'] = h.color.color_name if h.color_id else ''
    if 'coating' in columns:
        row['coating'] = h.coating.coating_name if h.coating_id else ''
    if 'capsule' in columns:
        row['capsule'] = h.capsule.capsule_name if h.capsule_id else ''
    if 'avg_wt' in columns:
        row['avg_wt'] = '' if h.avg_wt is None else str(h.avg_wt)
    if 'pkg_style' in columns:
        row['pkg_style'] = ''
    return row


def _row_pm(h: MstBomPmHed, columns: list[str]) -> dict:
    row = {}
    if 'bom_type' in columns:
        row['bom_type'] = 'PM'
    if 'spec_name' in columns:
        row['spec_name'] = h.spec_name
    if 'customer' in columns:
        row['customer'] = f"{h.customer.cust_name} ({h.customer.short_name})"
    if 'product' in columns:
        row['product'] = h.product.prod_name
    if 'machine' in columns:
        row['machine'] = h.machine.machine_name if h.machine_id else ''
    if 'no_of_lots' in columns:
        row['no_of_lots'] = '' if h.no_of_lots is None else str(h.no_of_lots)
    if 'batch_size' in columns:
        row['batch_size'] = str(h.batch_size)
    if 'batch_nos' in columns:
        row['batch_nos'] = str(h.batch_nos)
    if 'locked' in columns:
        row['locked'] = 'Yes' if h.is_locked else 'No'
    if 'shape' in columns:
        row['shape'] = ''
    if 'colour' in columns:
        row['colour'] = ''
    if 'coating' in columns:
        row['coating'] = ''
    if 'capsule' in columns:
        row['capsule'] = ''
    if 'avg_wt' in columns:
        row['avg_wt'] = ''
    if 'pkg_style' in columns:
        row['pkg_style'] = h.pkg_style.pkg_style_name if h.pkg_style_id else ''
    return row


def _row_rm_line(d: MstBomRmDtl, columns: list[str]) -> dict:
    row = {}
    if 'stage_name' in columns:
        row['stage_name'] = d.stage.stage_name
    if 'item_name' in columns:
        row['item_name'] = d.item.item_name
    if 'qty' in columns:
        row['qty'] = str(d.qty)
    if 'uom' in columns:
        row['uom'] = d.uom.short_name
    row['_qty_sort'] = d.qty
    return row


def _row_pm_line(d: MstBomPmDtl, columns: list[str]) -> dict:
    row = {}
    if 'stage_name' in columns:
        row['stage_name'] = d.stage.stage_name
    if 'item_name' in columns:
        row['item_name'] = d.item.item_name
    if 'qty' in columns:
        row['qty'] = str(d.qty)
    if 'uom' in columns:
        row['uom'] = d.uom.short_name
    row['_qty_sort'] = d.qty
    return row


def _with_sort_keys(row: dict) -> dict:
    try:
        row['_batch_sort'] = float(str(row.get('batch_size') or '0').replace(',', ''))
    except ValueError:
        row['_batch_sort'] = 0.0
    row['_locked_sort'] = 1 if (row.get('locked') == 'Yes') else 0
    return row


def _sort_combined(rows: list[dict], sort: dict, keys_map: dict, default_col: str) -> list[dict]:
    col = (sort or {}).get('column') or default_col
    direction = (sort or {}).get('dir') or 'asc'
    if col not in keys_map:
        col = default_col
    key_fn = keys_map[col]
    rev = direction == 'desc'
    return sorted(rows, key=key_fn, reverse=rev)


def _column_defs(keys: list[str]) -> list[dict]:
    labels = {
        'sr': 'Sr. No.',
        'bom_type': 'BOM type',
        'spec_name': 'Specification',
        'customer': 'Customer',
        'product': 'Product',
        'machine': 'Machine',
        'no_of_lots': 'No of Lots',
        'batch_size': 'Batch size (lakh)',
        'batch_nos': 'Batch nos.',
        'locked': 'Locked',
        'shape': 'Shape (RM)',
        'colour': 'Colour (RM)',
        'coating': 'Coating (RM)',
        'capsule': 'Capsule (RM)',
        'avg_wt': 'Avg. wt. (RM)',
        'pkg_style': 'Packing style (PM)',
        'stage_name': 'Stage',
        'item_name': 'Item',
        'qty': 'Quantity',
        'uom': 'UOM',
    }
    out = [{'key': 'sr', 'label': labels['sr']}]
    for k in keys:
        if k == 'sr':
            continue
        out.append({'key': k, 'label': labels.get(k, k)})
    return out


def _strip_internal(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith('_')}


def _normalize_spec_group_columns(columns: list) -> list[str]:
    allowed = set(_DEFAULT_BOM_SPEC_GROUP_COLUMNS)
    if not isinstance(columns, list) or not columns:
        return list(_DEFAULT_BOM_SPEC_GROUP_COLUMNS)
    out = [c for c in columns if c in allowed]
    return out if out else list(_DEFAULT_BOM_SPEC_GROUP_COLUMNS)


def _header_querysets(filters: dict, search: str | None):
    qs_rm = MstBomRmHed.objects.select_related(
        'customer', 'product', 'machine', 'shape', 'color', 'coating', 'capsule'
    ).order_by('spec_name')
    qs_pm = MstBomPmHed.objects.select_related('customer', 'product', 'pkg_style').order_by(
        'spec_name'
    )
    qs_rm = _apply_filters_rm(qs_rm, filters)
    qs_pm = _apply_filters_rm(qs_pm, filters)
    if search and search.strip():
        s = search.strip()
        qs_rm = qs_rm.filter(_search_q(s))
        qs_pm = qs_pm.filter(_search_q(s))
    kind_scope = _bom_kind_scope(filters)
    if kind_scope == 'pm':
        qs_rm = qs_rm.none()
    elif kind_scope == 'rm':
        qs_pm = qs_pm.none()
    return qs_rm, qs_pm


def run(payload: dict) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}
    search = (payload.get('search') or '').strip()
    sort = payload.get('sort')
    if not isinstance(sort, dict):
        sort = {}
    page = max(1, int(payload.get('page') or 1))
    per_page = min(100, max(5, int(payload.get('per_page') or 25)))
    export_mode = bool(payload.get('export'))

    if _bom_row_mode(filters) == 'spec_wise_items':
        columns = _normalize_spec_group_columns(payload.get('columns'))
        qs_rm, qs_pm = _header_querysets(filters, search=None)
        rm_ids = list(qs_rm.values_list('spec_id', flat=True))
        pm_ids = list(qs_pm.values_list('spec_id', flat=True))

        qs_dtl_rm = MstBomRmDtl.objects.select_related(
            'spec', 'spec__customer', 'spec__product', 'stage', 'item', 'uom'
        ).filter(spec_id__in=rm_ids)
        qs_dtl_pm = MstBomPmDtl.objects.select_related(
            'spec', 'spec__customer', 'spec__product', 'stage', 'item', 'uom'
        ).filter(spec_id__in=pm_ids)

        if search:
            s = search.strip()
            qs_dtl_rm = qs_dtl_rm.filter(_search_q_lines(s))
            qs_dtl_pm = qs_dtl_pm.filter(_search_q_lines(s))

        buckets: dict[tuple[str, int], list] = {}
        for d in qs_dtl_rm.order_by('spec_id', 'dtl_id'):
            buckets.setdefault(('RM', d.spec_id), []).append(d)
        for d in qs_dtl_pm.order_by('spec_id', 'dtl_id'):
            buckets.setdefault(('PM', d.spec_id), []).append(d)

        def _bucket_sort_key(k: tuple[str, int]):
            bt, _sid = k
            d0 = buckets[k][0]
            sp = d0.spec
            return (
                bt,
                (sp.spec_name or '').lower(),
                sp.customer.cust_name.lower(),
                sp.product.prod_name.lower(),
            )

        ordered_keys = sorted(buckets.keys(), key=_bucket_sort_key)
        total_line_count = sum(len(buckets[k]) for k in ordered_keys)
        total_groups = len(ordered_keys)
        group_page = max(1, int(payload.get('group_page') or page))
        group_per_page = min(50, max(1, int(payload.get('group_per_page') or 10)))
        if export_mode:
            slice_keys = ordered_keys
        else:
            start_g = (group_page - 1) * group_per_page
            slice_keys = ordered_keys[start_g : start_g + group_per_page]

        groups_out = []
        for key in slice_keys:
            dlist = buckets[key]
            sp = dlist[0].spec
            bt = key[0]
            header = (
                f"[{bt}] {sp.spec_name} — {sp.customer.cust_name} "
                f"({sp.customer.short_name}) — {sp.product.prod_name}"
            )
            g_rows_raw = []
            for d in dlist:
                if bt == 'RM':
                    g_rows_raw.append(_row_rm_line(d, columns))
                else:
                    g_rows_raw.append(_row_pm_line(d, columns))
            g_rows_raw = _sort_combined(g_rows_raw, sort, _SORT_KEYS_SPEC_GROUP, 'item_name')
            g_rows = []
            for idx, r in enumerate(g_rows_raw, start=1):
                r.pop('_qty_sort', None)
                out = _strip_internal(r)
                out['sr'] = idx
                g_rows.append(out)
            groups_out.append({'header': header, 'rows': g_rows})

        total_gpages = (
            (total_groups + group_per_page - 1) // group_per_page if total_groups else 1
        )
        return {
            'layout': 'grouped',
            'group_by': 'bom_spec',
            'columns': _column_defs(columns),
            'groups': groups_out,
            'total_groups': total_groups,
            'group_page': group_page,
            'group_per_page': group_per_page,
            'total_group_pages': max(1, total_gpages),
            'total_count': total_line_count,
        }

    columns = payload.get('columns')
    if not isinstance(columns, list) or not columns:
        columns = list(_DEFAULT_COLUMNS)
    else:
        columns = list(columns)

    qs_rm, qs_pm = _header_querysets(filters, search)

    combined: list[dict] = []
    for h in qs_rm:
        combined.append(_with_sort_keys(_row_rm(h, columns)))
    for h in qs_pm:
        combined.append(_with_sort_keys(_row_pm(h, columns)))

    combined = _sort_combined(combined, sort, _SORT_KEYS, 'spec_name')
    for r in combined:
        r.pop('_batch_sort', None)
        r.pop('_locked_sort', None)

    total = len(combined)

    if export_mode:
        rows = []
        for idx, r in enumerate(combined, start=1):
            out = _strip_internal(r)
            out['sr'] = idx
            rows.append(out)
        return {
            'layout': 'tabular',
            'group_by': 'none',
            'columns': _column_defs(columns),
            'rows': rows,
            'total_count': total,
            'page': 1,
            'per_page': total,
            'total_pages': 1,
        }

    start = (page - 1) * per_page
    slice_rows = combined[start : start + per_page]
    rows = []
    for idx, r in enumerate(slice_rows, start=start + 1):
        out = _strip_internal(r)
        out['sr'] = idx
        rows.append(out)

    total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        'layout': 'tabular',
        'group_by': 'none',
        'columns': _column_defs(columns),
        'rows': rows,
        'total_count': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    }


def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
    cols = result.get('columns') or []
    if result.get('layout') == 'grouped':
        exp_cols = [{'key': '__section__', 'label': 'Group'}] + cols
        keys = [c['key'] for c in exp_cols]
        rows = []
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
