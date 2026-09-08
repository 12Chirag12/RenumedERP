"""
Product attribute masters — multiple small tables on one report.

Optional: capsule types grouped by capsule size (reference: List of Capsule Types).
"""

from collections import defaultdict

from masters.models import (
    MstCapsule,
    MstCoatType,
    MstColor,
    MstItemType,
    MstProdCat,
    MstShape,
)

SLUG = 'product_attribute_master'
LABEL = 'Product Attribute Master'
DESCRIPTION = 'Reference lists for categories, types, shapes, colours, coatings, and capsule types.'

_TABLE_DEFS = {
    'prod_cat': {
        'title': 'Product category',
        'model': MstProdCat,
        'name_field': 'prod_cat_name',
        'order': ['prod_cat_name'],
    },
    'item_type': {
        'title': 'Product type',
        'model': MstItemType,
        'name_field': 'item_type_name',
        'order': ['item_type_name'],
    },
    'shape': {
        'title': 'Product shape',
        'model': MstShape,
        'name_field': 'shape_name',
        'order': ['shape_name'],
    },
    'color': {
        'title': 'Product colour',
        'model': MstColor,
        'name_field': 'color_name',
        'order': ['color_name'],
    },
    'coat_type': {
        'title': 'Coating type',
        'model': MstCoatType,
        'name_field': 'coating_name',
        'order': ['coating_name'],
    },
    'capsule': {
        'title': 'Capsule type',
        'model': MstCapsule,
        'name_field': 'capsule_name',
        'order': ['capsule_size', 'capsule_color'],
    },
}

_DEFAULT_TABLES = list(_TABLE_DEFS.keys())


def get_ui_config() -> dict:
    return {
        'slug': SLUG,
        'label': LABEL,
        'description': DESCRIPTION,
        'layout': 'multi_table',
        'group_by_options': [{'value': 'none', 'label': 'Separate attribute tables'}],
        'default_group_by': 'none',
        'filters': [
            {
                'key': 'attributes',
                'label': 'Product attributes',
                'kind': 'all_or_multiselect',
                'list_label': 'Select attributes',
            },
            {
                'key': 'capsule_group',
                'label': 'Capsule list style',
                'kind': 'capsule_layout',
                'options': [
                    {'value': 'flat', 'label': 'Flat list'},
                    {'value': 'by_size', 'label': 'Grouped by capsule size'},
                ],
            },
        ],
        'columns': [],
        'attribute_table_keys': [
            {'key': 'prod_cat', 'label': 'Product category'},
            {'key': 'item_type', 'label': 'Product type'},
            {'key': 'shape', 'label': 'Product shape'},
            {'key': 'color', 'label': 'Product colour'},
            {'key': 'coat_type', 'label': 'Coating type'},
            {'key': 'capsule', 'label': 'Capsule type'},
        ],
        'default_columns': [],
        'sortable': [],
        'default_sort': {},
    }


def filter_options_attributes():
    return [{'id': k, 'label': v['title']} for k, v in _TABLE_DEFS.items()]


def run(payload: dict) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}
    attr = filters.get('attributes') or {}
    if attr.get('mode') == 'select':
        keys = [str(x) for x in (attr.get('ids') or []) if str(x) in _TABLE_DEFS]
        if not keys:
            keys = list(_TABLE_DEFS.keys())
    else:
        keys = list(_TABLE_DEFS.keys())

    capsule_layout = 'flat'
    cg = filters.get('capsule_group') or {}
    if str(cg.get('value')) == 'by_size':
        capsule_layout = 'by_size'

    sections = []

    for table_key in keys:
        if table_key not in _TABLE_DEFS:
            continue
        spec = _TABLE_DEFS[table_key]
        model = spec['model']
        nf = spec['name_field']

        if table_key == 'capsule' and capsule_layout == 'by_size':
            rows_qs = model.objects.order_by('capsule_size', 'capsule_color')
            buckets = defaultdict(list)
            for obj in rows_qs:
                buckets[obj.capsule_size].append(obj)

            groups = []
            for size in sorted(buckets.keys(), key=lambda x: (len(str(x)), str(x))):
                objs = buckets[size]
                g_rows = []
                for idx, obj in enumerate(objs, start=1):
                    g_rows.append({'sr': idx, 'name': getattr(obj, nf)})
                groups.append({'header': f"Capsule Size : {size}", 'rows': g_rows})
            sections.append(
                {
                    'table_key': table_key,
                    'title': 'List of capsule types',
                    'layout': 'grouped',
                    'column_defs': [{'key': 'sr', 'label': 'Sr. No.'}, {'key': 'name', 'label': 'Description'}],
                    'groups': groups,
                }
            )
            continue

        rows_qs = model.objects.all().order_by(*spec['order'])
        rows = []
        for idx, obj in enumerate(rows_qs, start=1):
            rows.append({'sr': idx, 'name': getattr(obj, nf)})
        sections.append(
            {
                'table_key': table_key,
                'title': spec['title'],
                'layout': 'tabular',
                'column_defs': [{'key': 'sr', 'label': 'Sr. No.'}, {'key': 'name', 'label': spec['title']}],
                'rows': rows,
            }
        )

    return {
        'layout': 'multi_table',
        'sections': sections,
        'total_count': sum(
            len(s.get('rows') or [])
            + sum(len(g.get('rows') or []) for g in (s.get('groups') or []))
            for s in sections
        ),
    }
