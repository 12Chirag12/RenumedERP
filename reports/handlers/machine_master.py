"""Machine master report with optional section filter."""

from django.core.paginator import Paginator
from django.db.models import Q

from masters.models import MstMachine, MstSection

SLUG = 'machine_master'
LABEL = 'Machine Master'
DESCRIPTION = 'Machines with department and section; filter by manufacturing section.'

_DEFAULT_COLUMNS = [
    'machine_name',
    'section_name',
    'department_name',
    'make',
    'model_no',
    'machine_no',
    'capacity',
    'installed_date',
    'remarks',
]

_SORTABLE = {
    'machine_name': 'machine_name',
    'section_name': 'section__section_name',
    'department_name': 'section__department__dept_name',
    'make': 'make',
    'model_no': 'model_no',
    'machine_no': 'machine_no',
    'capacity': 'capacity',
    'installed_date': 'installed_date',
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
                'key': 'section',
                'label': 'Select Section',
                'kind': 'all_or_multiselect',
                'list_label': 'Sections',
            },
        ],
        'columns': [
            {'key': 'machine_name', 'label': 'Machine name', 'default': True},
            {'key': 'section_name', 'label': 'Section', 'default': True},
            {'key': 'department_name', 'label': 'Department', 'default': True},
            {'key': 'make', 'label': 'Make', 'default': True},
            {'key': 'model_no', 'label': 'Model no.', 'default': True},
            {'key': 'machine_no', 'label': 'Machine no.', 'default': True},
            {'key': 'capacity', 'label': 'Capacity', 'default': True},
            {'key': 'installed_date', 'label': 'Installation date', 'default': True},
            {'key': 'remarks', 'label': 'Remarks', 'default': False},
        ],
        'default_columns': _DEFAULT_COLUMNS,
        'sortable': list(_SORTABLE.keys()),
        'default_sort': {'column': 'machine_name', 'dir': 'asc'},
    }


def filter_options_section():
    qs = (
        MstSection.objects.select_related('department')
        .order_by('department__dept_name', 'section_name')
        .values('section_id', 'section_name', 'department__dept_name')
    )
    return [
        {
            'id': r['section_id'],
            'label': f"{r['section_name']} ({r['department__dept_name']})",
        }
        for r in qs
    ]


def _base_queryset(filters: dict, search: str):
    qs = MstMachine.objects.select_related('section', 'section__department').order_by('machine_name')

    sec = filters.get('section') or {}
    if sec.get('mode') == 'select':
        ids = [int(x) for x in (sec.get('ids') or []) if str(x).isdigit()]
        if ids:
            qs = qs.filter(section_id__in=ids)

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(machine_name__icontains=s)
                | Q(make__icontains=s)
                | Q(model_no__icontains=s)
                | Q(machine_no__icontains=s)
                | Q(section__section_name__icontains=s)
            )
    return qs


def _serialize(obj: MstMachine, columns: list[str]) -> dict:
    row = {}
    if 'machine_name' in columns:
        row['machine_name'] = obj.machine_name
    if 'section_name' in columns:
        row['section_name'] = obj.section.section_name
    if 'department_name' in columns:
        row['department_name'] = obj.section.department.dept_name
    if 'make' in columns:
        row['make'] = obj.make or ''
    if 'model_no' in columns:
        row['model_no'] = obj.model_no or ''
    if 'machine_no' in columns:
        row['machine_no'] = obj.machine_no or ''
    if 'capacity' in columns:
        row['capacity'] = obj.capacity or ''
    if 'installed_date' in columns:
        row['installed_date'] = obj.installed_date.isoformat() if obj.installed_date else ''
    if 'remarks' in columns:
        row['remarks'] = (obj.remarks or '').strip()
    return row


def _apply_sort(qs, sort: dict):
    col = (sort or {}).get('column') or 'machine_name'
    direction = (sort or {}).get('dir') or 'asc'
    if col not in _SORTABLE:
        col = 'machine_name'
    order = _SORTABLE[col]
    if direction == 'desc':
        order = f'-{order}'
    return qs.order_by(order)


def _column_defs(keys: list[str]) -> list[dict]:
    labels = {
        'sr': 'Sr. No.',
        'machine_name': 'Machine name',
        'section_name': 'Section',
        'department_name': 'Department',
        'make': 'Make',
        'model_no': 'Model no.',
        'machine_no': 'Machine no.',
        'capacity': 'Capacity',
        'installed_date': 'Installation date',
        'remarks': 'Remarks',
    }
    out = [{'key': 'sr', 'label': labels['sr']}]
    for k in keys:
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
