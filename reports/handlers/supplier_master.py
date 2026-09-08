"""Supplier master report — optional subset filter."""

from django.core.paginator import Paginator
from django.db.models import Q

from masters.models import MstSupplier

SLUG = 'supplier_master'
LABEL = 'Supplier Master'
DESCRIPTION = 'Supplier register with optional filter to include only selected suppliers.'

_DEFAULT_COLUMNS = [
    'supl_name',
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

_SORTABLE = {
    'supl_name': 'supl_name',
    'short_name': 'short_name',
    'state_name': 'state__state_name',
    'pin_code': 'pin_code',
    'email': 'email',
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
                'key': 'supplier',
                'label': 'Suppliers',
                'kind': 'all_or_multiselect',
                'list_label': 'Select suppliers',
            },
        ],
        'columns': [
            {'key': 'supl_name', 'label': 'Supplier name', 'default': True},
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
        'default_columns': _DEFAULT_COLUMNS,
        'sortable': list(_SORTABLE.keys()),
        'default_sort': {'column': 'supl_name', 'dir': 'asc'},
    }


def filter_options_supplier():
    qs = MstSupplier.objects.order_by('supl_name').values('supl_id', 'supl_name', 'short_name')
    out = []
    for r in qs:
        sn = (r.get('short_name') or '').strip()
        lab = r['supl_name'] if not sn else f"{r['supl_name']} ({sn})"
        out.append({'id': r['supl_id'], 'label': lab})
    return out


def _base_queryset(filters: dict, search: str):
    qs = MstSupplier.objects.select_related('state').order_by('supl_name')

    sup = filters.get('supplier') or {}
    if sup.get('mode') == 'select':
        ids = [int(x) for x in (sup.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(supl_id__in=ids)

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(supl_name__icontains=s)
                | Q(short_name__icontains=s)
                | Q(email__icontains=s)
                | Q(gst_no__icontains=s)
                | Q(mobile_no__icontains=s)
                | Q(state__state_name__icontains=s)
            )
    return qs


def _serialize(obj: MstSupplier, columns: list[str]) -> dict:
    row = {}
    if 'supl_name' in columns:
        row['supl_name'] = obj.supl_name
    if 'short_name' in columns:
        row['short_name'] = obj.short_name or ''
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


def _apply_sort(qs, sort: dict):
    col = (sort or {}).get('column') or 'supl_name'
    direction = (sort or {}).get('dir') or 'asc'
    if col not in _SORTABLE:
        col = 'supl_name'
    order = _SORTABLE[col]
    if direction == 'desc':
        order = f'-{order}'
    return qs.order_by(order)


def _column_defs(keys: list[str]) -> list[dict]:
    labels = {
        'sr': 'Sr. No.',
        'supl_name': 'Supplier name',
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
    }
    out = [{'key': 'sr', 'label': labels['sr']}]
    for k in keys:
        if k == 'sr':
            continue
        out.append({'key': k, 'label': labels.get(k, k)})
    return out


def run(payload: dict) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}
    columns = payload.get('columns')
    if not isinstance(columns, list) or not columns:
        columns = list(_DEFAULT_COLUMNS)
    else:
        columns = list(columns)
    search = (payload.get('search') or '').strip()
    sort = payload.get('sort')
    if not isinstance(sort, dict):
        sort = {}
    page = max(1, int(payload.get('page') or 1))
    per_page = min(100, max(5, int(payload.get('per_page') or 25)))
    export_mode = bool(payload.get('export'))

    qs = _apply_sort(_base_queryset(filters, search), sort)

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
    return result.get('columns') or [], result.get('rows') or []
