"""Customer master report — optional subset filter; customer-wise product list grouped by customer (MstCustProd)."""

from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Q

from masters.models import MstCust, MstCustProd

SLUG = 'customer_master'
LABEL = 'Customer Master'
DESCRIPTION = (
    'Customer register with optional filters. Customer-wise product list shows linked products '
    'under each customer (like specification-wise BOM items).'
)

_DEFAULT_COLUMNS = [
    'cust_name',
    'short_name',
    'address',
    'state_name',
    'pin_code',
    'landline_no',
    'mobile_no',
    'email',
    'pan_no',
    'gst_no',
    'udyam_cert',
]

# Inner table only (customer name is the group header)
_DEFAULT_CUSTOMER_PROD_INNER = [
    'prod_name',
    'generic_name',
    'batch_abbr',
    'adv_license',
    'license_details',
]

_SORTABLE = {
    'cust_name': 'cust_name',
    'short_name': 'short_name',
    'state_name': 'state__state_name',
    'pin_code': 'pin_code',
    'email': 'email',
}

_SORT_KEYS_CUST_PROD_INNER = {
    'prod_name': lambda r: (r.get('prod_name') or '').lower(),
    'generic_name': lambda r: (r.get('generic_name') or '').lower(),
    'batch_abbr': lambda r: (r.get('batch_abbr') or '').lower(),
    'adv_license': lambda r: (r.get('adv_license') or '').lower(),
    'license_details': lambda r: (r.get('license_details') or '').lower(),
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
                'key': 'customer_view',
                'label': 'View',
                'kind': 'radio_choice',
                'input_name': 'mr_customer_view',
                'radio_layout': 'vertical',
                'options': [
                    {'value': 'master', 'label': 'Customers (master)'},
                    {'value': 'customer_products', 'label': 'Customer-wise product list'},
                ],
            },
            {
                'key': 'customer',
                'label': 'Customers',
                'kind': 'all_or_multiselect',
                'list_label': 'Select customers',
            },
        ],
        'columns': [
            {'key': 'cust_name', 'label': 'Customer name', 'default': True},
            {'key': 'short_name', 'label': 'Short name', 'default': True},
            {'key': 'address', 'label': 'Address', 'default': True},
            {'key': 'state_name', 'label': 'State', 'default': True},
            {'key': 'pin_code', 'label': 'PIN code', 'default': True},
            {'key': 'landline_no', 'label': 'Land line', 'default': False},
            {'key': 'mobile_no', 'label': 'Mobile', 'default': True},
            {'key': 'email', 'label': 'Email', 'default': True},
            {'key': 'pan_no', 'label': 'PAN', 'default': False},
            {'key': 'gst_no', 'label': 'GST', 'default': True},
            {'key': 'udyam_cert', 'label': 'Udyam', 'default': False},
        ],
        'columns_customer_products': [
            {'key': 'prod_name', 'label': 'Product', 'default': True},
            {'key': 'generic_name', 'label': 'Generic name', 'default': True},
            {'key': 'batch_abbr', 'label': 'Batch abbreviation', 'default': True},
            {'key': 'adv_license', 'label': 'Advance licence', 'default': True},
            {'key': 'license_details', 'label': 'Licence details', 'default': False},
        ],
        'default_columns': _DEFAULT_COLUMNS,
        'default_columns_customer_products': _DEFAULT_CUSTOMER_PROD_INNER,
        'sortable': list(_SORTABLE.keys()),
        'sortable_customer_products': list(_SORT_KEYS_CUST_PROD_INNER.keys()),
        'default_sort': {'column': 'cust_name', 'dir': 'asc'},
        'default_sort_customer_products': {'column': 'prod_name', 'dir': 'asc'},
    }


def filter_options_customer():
    qs = MstCust.objects.order_by('cust_name').values('cust_id', 'cust_name', 'short_name')
    return [
        {'id': r['cust_id'], 'label': f"{r['cust_name']} ({r['short_name']})"}
        for r in qs
    ]


def _customer_view_mode(filters: dict) -> str:
    cv = filters.get('customer_view') or {}
    v = str(cv.get('value') or 'master').strip().lower()
    if v == 'customer_products':
        return 'customer_products'
    return 'master'


def _base_queryset(filters: dict, search: str):
    qs = MstCust.objects.select_related('state').order_by('cust_name')

    cust = filters.get('customer') or {}
    if cust.get('mode') == 'select':
        ids = [int(x) for x in (cust.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(cust_id__in=ids)

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(cust_name__icontains=s)
                | Q(short_name__icontains=s)
                | Q(email__icontains=s)
                | Q(gst_no__icontains=s)
                | Q(mobile_no__icontains=s)
                | Q(state__state_name__icontains=s)
            )
    return qs


def _cust_prod_queryset(filters: dict, search: str):
    qs = MstCustProd.objects.select_related('customer', 'customer__state', 'product').order_by(
        'customer__cust_name', 'product__prod_name'
    )

    cust = filters.get('customer') or {}
    if cust.get('mode') == 'select':
        ids = [int(x) for x in (cust.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(customer_id__in=ids)

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(customer__cust_name__icontains=s)
                | Q(customer__short_name__icontains=s)
                | Q(product__prod_name__icontains=s)
                | Q(product__generic_name__icontains=s)
                | Q(batch_abbr__icontains=s)
                | Q(license_details__icontains=s)
            )
    return qs


def _serialize(obj: MstCust, columns: list[str]) -> dict:
    row = {}
    if 'cust_name' in columns:
        row['cust_name'] = obj.cust_name
    if 'short_name' in columns:
        row['short_name'] = obj.short_name
    if 'address' in columns:
        row['address'] = (obj.address or '').strip()
    if 'state_name' in columns:
        row['state_name'] = obj.state.state_name if obj.state_id else ''
    if 'pin_code' in columns:
        row['pin_code'] = obj.pin_code or ''
    if 'landline_no' in columns:
        row['landline_no'] = obj.landline_no or ''
    if 'mobile_no' in columns:
        row['mobile_no'] = obj.mobile_no or ''
    if 'email' in columns:
        row['email'] = obj.email or ''
    if 'pan_no' in columns:
        row['pan_no'] = obj.pan_no or ''
    if 'gst_no' in columns:
        row['gst_no'] = obj.gst_no or ''
    if 'udyam_cert' in columns:
        row['udyam_cert'] = obj.udyam_cert or ''
    return row


def _serialize_cust_prod_line(obj: MstCustProd, columns: list[str]) -> dict:
    p = obj.product
    row = {}
    if 'prod_name' in columns:
        row['prod_name'] = p.prod_name
    if 'generic_name' in columns:
        row['generic_name'] = (p.generic_name or '').strip()
    if 'batch_abbr' in columns:
        row['batch_abbr'] = obj.batch_abbr
    if 'adv_license' in columns:
        row['adv_license'] = obj.adv_license or ''
    if 'license_details' in columns:
        row['license_details'] = (obj.license_details or '').strip()
    return row


def _apply_sort(qs, sort: dict, sortable: dict, default_col: str):
    col = (sort or {}).get('column') or default_col
    direction = (sort or {}).get('dir') or 'asc'
    if col not in sortable:
        col = default_col
    order = sortable[col]
    if direction == 'desc':
        order = f'-{order}'
    return qs.order_by(order)


def _sort_inner_rows(rows: list[dict], sort: dict, keys_map: dict, default_col: str) -> list[dict]:
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
        'cust_name': 'Customer name',
        'short_name': 'Short name',
        'address': 'Address',
        'state_name': 'State',
        'pin_code': 'PIN code',
        'landline_no': 'Land line',
        'mobile_no': 'Mobile',
        'email': 'Email',
        'pan_no': 'PAN',
        'gst_no': 'GST',
        'udyam_cert': 'Udyam',
        'prod_name': 'Product',
        'generic_name': 'Generic name',
        'batch_abbr': 'Batch abbreviation',
        'adv_license': 'Advance licence',
        'license_details': 'Licence details',
    }
    out = [{'key': 'sr', 'label': labels['sr']}]
    for k in keys:
        if k == 'sr':
            continue
        out.append({'key': k, 'label': labels.get(k, k)})
    return out


def _normalize_columns(columns: list, allowed: list[str], fallback: list[str]) -> list[str]:
    if not isinstance(columns, list) or not columns:
        return list(fallback)
    out = [c for c in columns if c in allowed]
    return out if out else list(fallback)


def _normalize_customer_prod_inner(columns: list) -> list[str]:
    allowed = set(_DEFAULT_CUSTOMER_PROD_INNER)
    if not isinstance(columns, list) or not columns:
        return list(_DEFAULT_CUSTOMER_PROD_INNER)
    out = [c for c in columns if c in allowed]
    return out if out else list(_DEFAULT_CUSTOMER_PROD_INNER)


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

    if _customer_view_mode(filters) == 'customer_products':
        columns = _normalize_customer_prod_inner(payload.get('columns'))
        qs = _cust_prod_queryset(filters, search)
        qs_list = list(qs.order_by('customer__cust_name', 'product__prod_name'))
        buckets: dict[int, list[MstCustProd]] = defaultdict(list)
        ordered_cust_ids: list[int] = []
        seen: set[int] = set()
        for obj in qs_list:
            buckets[obj.customer_id].append(obj)
            if obj.customer_id not in seen:
                seen.add(obj.customer_id)
                ordered_cust_ids.append(obj.customer_id)

        total_line_count = len(qs_list)
        total_groups = len(ordered_cust_ids)
        group_page = max(1, int(payload.get('group_page') or page))
        group_per_page = min(50, max(1, int(payload.get('group_per_page') or 10)))
        if export_mode:
            slice_ids = ordered_cust_ids
        else:
            start_g = (group_page - 1) * group_per_page
            slice_ids = ordered_cust_ids[start_g : start_g + group_per_page]

        cust_map = MstCust.objects.in_bulk(slice_ids)
        groups_out = []
        for cid in slice_ids:
            cust = cust_map.get(cid)
            if not cust:
                continue
            header = f"Customer : {cust.cust_name} ({cust.short_name})"
            lines = buckets[cid]
            g_rows_raw = [_serialize_cust_prod_line(obj, columns) for obj in lines]
            g_rows_raw = _sort_inner_rows(
                g_rows_raw, sort, _SORT_KEYS_CUST_PROD_INNER, 'prod_name'
            )
            g_rows = []
            for idx, r in enumerate(g_rows_raw, start=1):
                r2 = dict(r)
                r2['sr'] = idx
                g_rows.append(r2)
            groups_out.append({'header': header, 'rows': g_rows})

        total_gpages = (
            (total_groups + group_per_page - 1) // group_per_page if total_groups else 1
        )
        return {
            'layout': 'grouped',
            'group_by': 'customer_products',
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
    qs = _apply_sort(_base_queryset(filters, search), sort, _SORTABLE, 'cust_name')

    if export_mode:
        items = list(qs)
        rows = []
        for idx, obj in enumerate(items, start=1):
            r = _serialize(obj, columns)
            r['sr'] = idx
            rows.append(r)
        return {
            'layout': 'tabular',
            'group_by': 'none',
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
        r = _serialize(obj, columns)
        r['sr'] = idx
        rows.append(r)

    return {
        'layout': 'tabular',
        'group_by': 'none',
        'columns': _column_defs(columns),
        'rows': rows,
        'total_count': paginator.count,
        'page': pg.number,
        'per_page': per_page,
        'total_pages': paginator.num_pages,
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
