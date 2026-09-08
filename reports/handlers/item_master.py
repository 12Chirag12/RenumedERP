"""Item (RM/PM) master report — filter by item category and item type."""

from django.core.paginator import Paginator
from django.db.models import Q

from masters.models import MstItem, MstItemType, MstProdCat

SLUG = 'item_master'
LABEL = 'Item Master'
DESCRIPTION = 'Item register with optional filters by item category and item type.'

_DEFAULT_COLUMNS = [
    'item_name',
    'item_category',
    'item_type',
    'uom',
    'hsn_code',
    'min_level',
    'max_level',
    'maintain_batch',
    'mfg_date',
    'exp_date',
    'last_purchase_rate',
]

_SORTABLE = {
    'item_name': 'item_name',
    'item_category': 'item_category__prod_cat_name',
    'item_type': 'item_type__item_type_name',
    'hsn_code': 'hsn_code',
    'last_purchase_rate': 'last_purchase_rate',
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
                'key': 'item_category',
                'label': 'Item category',
                'kind': 'all_or_multiselect',
                'list_label': 'Select categories',
            },
            {
                'key': 'item_type',
                'label': 'Item type',
                'kind': 'all_or_multiselect',
                'list_label': 'Select item types',
            },
        ],
        'columns': [
            {'key': 'item_name', 'label': 'Item name', 'default': True},
            {'key': 'item_category', 'label': 'Item category', 'default': True},
            {'key': 'item_type', 'label': 'Item type', 'default': True},
            {'key': 'uom', 'label': 'UOM', 'default': True},
            {'key': 'hsn_code', 'label': 'HSN code', 'default': True},
            {'key': 'min_level', 'label': 'Min. stock level', 'default': False},
            {'key': 'max_level', 'label': 'Max. stock level', 'default': False},
            {'key': 'maintain_batch', 'label': 'Maintain batch', 'default': True},
            {'key': 'mfg_date', 'label': 'Mfg date', 'default': False},
            {'key': 'exp_date', 'label': 'Expiry date', 'default': False},
            {'key': 'last_purchase_rate', 'label': 'Last purchase rate', 'default': False},
        ],
        'default_columns': _DEFAULT_COLUMNS,
        'sortable': list(_SORTABLE.keys()),
        'default_sort': {'column': 'item_name', 'dir': 'asc'},
    }


def filter_options_item_category():
    qs = MstProdCat.objects.order_by('prod_cat_name').values('prod_cat_id', 'prod_cat_name')
    return [{'id': r['prod_cat_id'], 'label': r['prod_cat_name']} for r in qs]


def filter_options_item_type():
    qs = (
        MstItemType.objects.select_related('item_category')
        .order_by('item_category__prod_cat_name', 'item_type_name')
        .values('item_type_id', 'item_type_name', 'item_category__prod_cat_name')
    )
    return [
        {
            'id': r['item_type_id'],
            'label': f"{r['item_type_name']} ({r['item_category__prod_cat_name']})",
        }
        for r in qs
    ]


def _base_queryset(filters: dict, search: str):
    qs = MstItem.objects.select_related('item_type', 'item_category', 'uom').order_by('item_name')

    ic = filters.get('item_category') or {}
    if ic.get('mode') == 'select':
        ids = [str(x).strip() for x in (ic.get('ids') or []) if str(x).strip()]
        if ids:
            qs = qs.filter(item_category_id__in=ids)

    it = filters.get('item_type') or {}
    if it.get('mode') == 'select':
        ids = [int(x) for x in (it.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(item_type_id__in=ids)

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(item_name__icontains=s)
                | Q(hsn_code__icontains=s)
                | Q(item_type__item_type_name__icontains=s)
                | Q(item_category__prod_cat_name__icontains=s)
            )
    return qs


def _serialize(obj: MstItem, columns: list[str]) -> dict:
    row = {}
    if 'item_name' in columns:
        row['item_name'] = obj.item_name
    if 'item_category' in columns:
        row['item_category'] = obj.item_category.prod_cat_name if obj.item_category_id else ''
    if 'item_type' in columns:
        row['item_type'] = obj.item_type.item_type_name if obj.item_type_id else ''
    if 'uom' in columns:
        row['uom'] = obj.uom.short_name if obj.uom_id else ''
    if 'hsn_code' in columns:
        row['hsn_code'] = obj.hsn_code or ''
    if 'min_level' in columns:
        row['min_level'] = '' if obj.min_level is None else str(obj.min_level)
    if 'max_level' in columns:
        row['max_level'] = '' if obj.max_level is None else str(obj.max_level)
    if 'maintain_batch' in columns:
        row['maintain_batch'] = obj.maintain_batch or ''
    if 'mfg_date' in columns:
        row['mfg_date'] = obj.mfg_date or ''
    if 'exp_date' in columns:
        row['exp_date'] = obj.exp_date or ''
    if 'last_purchase_rate' in columns:
        row['last_purchase_rate'] = str(obj.last_purchase_rate)
    return row


def _apply_sort(qs, sort: dict):
    col = (sort or {}).get('column') or 'item_name'
    direction = (sort or {}).get('dir') or 'asc'
    if col not in _SORTABLE:
        col = 'item_name'
    order = _SORTABLE[col]
    if direction == 'desc':
        order = f'-{order}'
    return qs.order_by(order)


def _column_defs(keys: list[str]) -> list[dict]:
    labels = {
        'sr': 'Sr. No.',
        'item_name': 'Item name',
        'item_category': 'Item category',
        'item_type': 'Item type',
        'uom': 'UOM',
        'hsn_code': 'HSN code',
        'min_level': 'Min. stock level',
        'max_level': 'Max. stock level',
        'maintain_batch': 'Maintain batch',
        'mfg_date': 'Mfg date',
        'exp_date': 'Expiry date',
        'last_purchase_rate': 'Last purchase rate',
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
