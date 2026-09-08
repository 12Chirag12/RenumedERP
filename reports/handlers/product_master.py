"""
Product master report — flat list, customer-wise, or product-type-wise grouping.

Data model: MstProd + MstCustProd for customer short names.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Prefetch, Q

from masters.models import MstCust, MstCustProd, MstItemType, MstProd

SLUG = 'product_master'
LABEL = 'Product Master'
DESCRIPTION = 'Product register with optional filters by type and customer, grouping, and column selection.'

_GROUP_NONE = 'none'
_GROUP_CUSTOMER = 'customer'
_GROUP_TYPE = 'product_type'

_DEFAULT_COLUMNS = [
    'prod_name',
    'generic_name',
    'product_type',
    'uom',
    'hsn_code',
    'tablet_layer',
    'first_color',
    'second_color',
    'customer',
]

_SORTABLE = {
    'prod_name': 'prod_name',
    'product_type': 'prod_type__item_type_name',
    'uom': 'uom__short_name',
    'hsn_code': 'hsn_code',
    'tablet_layer': 'tablet_layer',
    'first_color': 'first_color__color_name',
    'second_color': 'second_color__color_name',
    'customer': 'prod_name',  # fallback when sorting by customer (flat only)
}


def get_ui_config() -> dict:
    return {
        'slug': SLUG,
        'label': LABEL,
        'description': DESCRIPTION,
        'layout': 'tabular',
        'group_by_options': [
            {'value': _GROUP_NONE, 'label': 'Product List (flat)'},
            {'value': _GROUP_CUSTOMER, 'label': 'Product List — Customer wise'},
            {'value': _GROUP_TYPE, 'label': 'Product List — Type wise'},
        ],
        'default_group_by': _GROUP_NONE,
        'filters': [
            {
                'key': 'item_type',
                'label': 'Select Type',
                'kind': 'all_or_multiselect',
                'list_label': 'Product types',
            },
            {
                'key': 'customer',
                'label': 'Select Customer',
                'kind': 'all_or_multiselect',
                'list_label': 'Customers',
            },
        ],
        'columns': [
            {'key': 'prod_name', 'label': 'Product name', 'default': True},
            {'key': 'generic_name', 'label': 'Generic name', 'default': True},
            {'key': 'product_type', 'label': 'Product type', 'default': True},
            {'key': 'uom', 'label': 'UOM', 'default': True},
            {'key': 'hsn_code', 'label': 'HSN', 'default': True},
            {'key': 'tablet_layer', 'label': 'Layer type', 'default': True},
            {'key': 'first_color', 'label': 'First colour', 'default': True},
            {'key': 'second_color', 'label': 'Second colour', 'default': True},
            {'key': 'customer', 'label': 'Customer', 'default': True},
        ],
        'default_columns': _DEFAULT_COLUMNS,
        'sortable': list(_SORTABLE.keys()),
        'default_sort': {'column': 'prod_name', 'dir': 'asc'},
    }


def filter_options_item_type():
    qs = MstItemType.objects.order_by('item_type_name').values('item_type_id', 'item_type_name')
    return [{'id': r['item_type_id'], 'label': r['item_type_name']} for r in qs]


def filter_options_customer():
    qs = MstCust.objects.order_by('cust_name').values('cust_id', 'cust_name', 'short_name')
    return [
        {'id': r['cust_id'], 'label': f"{r['cust_name']} ({r['short_name']})"}
        for r in qs
    ]


def filter_options_product():
    qs = MstProd.objects.order_by('prod_name').values('prod_id', 'prod_name')
    return [{'id': r['prod_id'], 'label': r['prod_name']} for r in qs]


def _base_queryset(filters: dict, search: str):
    qs = (
        MstProd.objects.select_related(
            'prod_type', 'uom', 'first_color', 'second_color', 'prod_category'
        )
        .prefetch_related(
            Prefetch(
                'cust_products',
                queryset=MstCustProd.objects.select_related('customer').order_by(
                    'customer__short_name'
                ),
            )
        )
        .order_by('prod_name')
    )

    it = filters.get('item_type') or {}
    if it.get('mode') == 'select':
        ids = [int(x) for x in (it.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(prod_type_id__in=ids)

    cu = filters.get('customer') or {}
    if cu.get('mode') == 'select':
        ids = [int(x) for x in (cu.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(cust_products__customer_id__in=ids).distinct()

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(prod_name__icontains=s)
                | Q(generic_name__icontains=s)
                | Q(hsn_code__icontains=s)
            )
    return qs


def _customers_display(obj: MstProd) -> str:
    names = []
    seen = set()
    for cp in obj.cust_products.all():
        sn = cp.customer.short_name
        if sn not in seen:
            seen.add(sn)
            names.append(sn)
    return ', '.join(names) if names else '—'


def _serialize_product(obj: MstProd, columns: list[str]) -> dict:
    row = {}
    if 'prod_name' in columns:
        row['prod_name'] = obj.prod_name
    if 'generic_name' in columns:
        row['generic_name'] = (obj.generic_name or '').strip()
    if 'product_type' in columns:
        row['product_type'] = obj.prod_type.item_type_name
    if 'uom' in columns:
        row['uom'] = obj.uom.short_name
    if 'hsn_code' in columns:
        row['hsn_code'] = obj.hsn_code or ''
    if 'tablet_layer' in columns:
        row['tablet_layer'] = obj.get_tablet_layer_display()
    if 'first_color' in columns:
        row['first_color'] = obj.first_color.color_name if obj.first_color else ''
    if 'second_color' in columns:
        row['second_color'] = obj.second_color.color_name if obj.second_color else ''
    if 'customer' in columns:
        row['customer'] = _customers_display(obj)
    return row


def _apply_sort(qs, sort: dict):
    col = (sort or {}).get('column') or 'prod_name'
    direction = (sort or {}).get('dir') or 'asc'
    if col not in _SORTABLE:
        col = 'prod_name'
    order = _SORTABLE[col]
    if direction == 'desc':
        order = f'-{order}'
    return qs.order_by(order)


def _effective_columns(columns: list[str] | None, group_by: str) -> list[str]:
    cols = list(columns) if columns else list(_DEFAULT_COLUMNS)
    if group_by == _GROUP_CUSTOMER and 'customer' in cols:
        cols = [c for c in cols if c != 'customer']
    if group_by == _GROUP_TYPE and 'product_type' in cols:
        cols = [c for c in cols if c != 'product_type']
    return cols


def run(payload: dict) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}
    group_by = payload.get('group_by') or _GROUP_NONE
    if group_by not in {_GROUP_NONE, _GROUP_CUSTOMER, _GROUP_TYPE}:
        group_by = _GROUP_NONE

    columns = payload.get('columns')
    if columns is not None and not isinstance(columns, list):
        columns = None
    columns = _effective_columns(columns, group_by)
    search = (payload.get('search') or '').strip()
    sort = payload.get('sort')
    if not isinstance(sort, dict):
        sort = {}
    page = max(1, int(payload.get('page') or 1))
    per_page = min(100, max(5, int(payload.get('per_page') or 25)))
    export_mode = bool(payload.get('export'))

    qs = _apply_sort(_base_queryset(filters, search), sort)

    if group_by == _GROUP_NONE:
        if export_mode:
            items = list(qs)
            rows = []
            for idx, obj in enumerate(items, start=1):
                r = _serialize_product(obj, columns)
                r['sr'] = idx
                rows.append(r)
            return {
                'layout': 'tabular',
                'group_by': group_by,
                'columns': _column_defs(columns),
                'rows': rows,
                'total_count': len(rows),
                'page': 1,
                'per_page': len(rows),
                'total_pages': 1,
            }

        paginator = Paginator(qs, per_page)
        pg = paginator.get_page(page)
        rows = []
        start = (pg.number - 1) * per_page
        for idx, obj in enumerate(pg.object_list, start=start + 1):
            r = _serialize_product(obj, columns)
            r['sr'] = idx
            rows.append(r)
        return {
            'layout': 'tabular',
            'group_by': group_by,
            'columns': _column_defs(columns),
            'rows': rows,
            'total_count': paginator.count,
            'page': pg.number,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
        }

    # Grouped modes — paginate by group (customer or product type label)
    if group_by == _GROUP_CUSTOMER:
        cust_ids = list(
            MstCust.objects.filter(cust_products__product__in=qs)
            .order_by('cust_name')
            .distinct()
            .values_list('cust_id', flat=True)
        )
    else:
        type_ids = list(
            MstItemType.objects.filter(products__in=qs)
            .order_by('item_type_name')
            .distinct()
            .values_list('item_type_id', flat=True)
        )

    if group_by == _GROUP_CUSTOMER:
        total_groups = len(cust_ids)
        group_page = max(1, int(payload.get('group_page') or page))
        group_per_page = min(50, max(1, int(payload.get('group_per_page') or 10)))
        if export_mode:
            slice_ids = cust_ids
            group_page = 1
            group_per_page = len(cust_ids) or 1
        else:
            start_g = (group_page - 1) * group_per_page
            slice_ids = cust_ids[start_g : start_g + group_per_page]

        groups_out = []
        for cid in slice_ids:
            cust = MstCust.objects.filter(pk=cid).first()
            if not cust:
                continue
            header = f"Customer Name : {cust.cust_name}"
            prod_ids = (
                MstCustProd.objects.filter(customer_id=cid, product__in=qs)
                .values_list('product_id', flat=True)
                .distinct()
            )
            sub_qs = _apply_sort(qs.filter(prod_id__in=prod_ids), sort)
            g_rows = []
            for idx, obj in enumerate(sub_qs, start=1):
                r = _serialize_product(obj, columns)
                r['sr'] = idx
                g_rows.append(r)
            groups_out.append({'header': header, 'rows': g_rows})

        total_pages = (
            (total_groups + group_per_page - 1) // group_per_page if total_groups else 1
        )
        return {
            'layout': 'grouped',
            'group_by': group_by,
            'columns': _column_defs(columns),
            'groups': groups_out,
            'total_groups': total_groups,
            'group_page': group_page,
            'group_per_page': group_per_page,
            'total_group_pages': max(1, total_pages),
            'total_count': qs.count(),
        }

    # product_type grouping
    total_groups = len(type_ids)
    group_page = max(1, int(payload.get('group_page') or page))
    group_per_page = min(50, max(1, int(payload.get('group_per_page') or 10)))
    if export_mode:
        slice_ids = type_ids
    else:
        start_g = (group_page - 1) * group_per_page
        slice_ids = type_ids[start_g : start_g + group_per_page]

    groups_out = []
    for tid in slice_ids:
        it = MstItemType.objects.filter(pk=tid).first()
        if not it:
            continue
        header = f"Product Type : {it.item_type_name}"
        sub_qs = _apply_sort(qs.filter(prod_type_id=tid), sort)
        g_rows = []
        for idx, obj in enumerate(sub_qs, start=1):
            r = _serialize_product(obj, columns)
            r['sr'] = idx
            g_rows.append(r)
        groups_out.append({'header': header, 'rows': g_rows})

    total_pages = (total_groups + group_per_page - 1) // group_per_page if total_groups else 1
    return {
        'layout': 'grouped',
        'group_by': group_by,
        'columns': _column_defs(columns),
        'groups': groups_out,
        'total_groups': total_groups,
        'group_page': group_page,
        'group_per_page': group_per_page,
        'total_group_pages': max(1, total_pages),
        'total_count': qs.count(),
    }


def _column_defs(keys: list[str]) -> list[dict]:
    labels = {
        'sr': 'Sr. No.',
        'prod_name': 'Product name',
        'generic_name': 'Generic name',
        'product_type': 'Product type',
        'uom': 'UOM',
        'hsn_code': 'HSN',
        'tablet_layer': 'Layer type',
        'first_color': 'First colour',
        'second_color': 'Second colour',
        'customer': 'Customer',
    }
    out = [{'key': 'sr', 'label': labels['sr']}]
    for k in keys:
        if k == 'sr':
            continue
        out.append({'key': k, 'label': labels.get(k, k)})
    return out


def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
    """Return (column_defs, rows) for Excel where grouped layout becomes flat with a header row marker."""
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
