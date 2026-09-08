"""
Reports app views: master reports hub, transaction reports hub, and JSON/export APIs.

Access: group permissions ``reports.master`` / ``reports.transaction`` (middleware).
"""

import json
from django.urls import reverse

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .handlers import (
    bom_master,
    customer_master,
    item_master,
    machine_master,
    product_attributes,
    product_master,
    supplier_master,
)
from .handlers.transactions.daily_production_report import (
    DailyProductionReport,
    filter_options_dpr_section,
)
from .handlers.transactions.inward_grn_receipt import (
    InwardGrnReceiptReport,
    filter_options_inward_grn,
)
from .handlers.transactions.inward_raw_material_register import (
    InwardRmRegisterFull,
    InwardRmRegisterStandard,
    filter_options_grn_category,
)
from .registry import get_handler, list_reports_meta
from . import transaction_registry
from .services.excel_export import build_product_attributes_workbook, build_workbook
from .services.meta import COMPANY_NAME_DEFAULT, report_run_meta

_INWARD_REGISTER_SLUGS = frozenset({InwardRmRegisterFull.SLUG, InwardRmRegisterStandard.SLUG})


def _login_required(view_func):
    from django.contrib.auth.decorators import login_required

    return login_required(view_func)


def _json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return None


@_login_required
def master_reports_page(request):
    cat = []
    for meta in list_reports_meta():
        row = dict(meta)
        row['config_url'] = reverse('master_report_config', kwargs={'slug': meta['slug']})
        cat.append(row)
    return render(
        request,
        'reports/master_reports.html',
        {
            'reports_catalogue': cat,
            'company_header': getattr(
                settings,
                'REPORT_COMPANY_HEADER',
                COMPANY_NAME_DEFAULT,
            ),
            'api_options_url': reverse('master_report_options'),
            'api_data_url': reverse('master_report_data'),
            'api_excel_url': reverse('master_report_export_excel'),
        },
    )


@_login_required
@require_GET
def master_report_config(request, slug):
    h = get_handler(slug)
    if not h or not hasattr(h, 'get_ui_config'):
        return JsonResponse({'error': 'Unknown report.'}, status=404)
    cfg = h.get_ui_config()
    return JsonResponse(cfg)


@_login_required
@require_GET
def master_report_options(request):
    slug = request.GET.get('report') or ''
    fk = request.GET.get('filter') or ''

    if slug == product_master.SLUG:
        if fk == 'item_type':
            return JsonResponse({'options': product_master.filter_options_item_type()})
        if fk == 'customer':
            return JsonResponse({'options': product_master.filter_options_customer()})
    if slug == machine_master.SLUG:
        if fk == 'section':
            return JsonResponse({'options': machine_master.filter_options_section()})
    if slug == product_attributes.SLUG:
        if fk == 'attributes':
            return JsonResponse({'options': product_attributes.filter_options_attributes()})
    if slug == customer_master.SLUG and fk == 'customer':
        return JsonResponse({'options': customer_master.filter_options_customer()})
    if slug == supplier_master.SLUG and fk == 'supplier':
        return JsonResponse({'options': supplier_master.filter_options_supplier()})
    if slug == bom_master.SLUG:
        if fk == 'customer':
            return JsonResponse({'options': product_master.filter_options_customer()})
        if fk == 'product':
            return JsonResponse({'options': product_master.filter_options_product()})
    if slug == item_master.SLUG:
        if fk == 'item_category':
            return JsonResponse({'options': item_master.filter_options_item_category()})
        if fk == 'item_type':
            return JsonResponse({'options': item_master.filter_options_item_type()})

    return JsonResponse({'options': []})


@_login_required
@require_POST
def master_report_data(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    slug = body.get('report') or ''
    h = get_handler(slug)
    if not h or not hasattr(h, 'run'):
        return JsonResponse({'error': 'Unknown report.'}, status=404)

    payload = {k: v for k, v in body.items() if k != 'report'}
    payload['export'] = False

    try:
        result = h.run(payload)
    except Exception as exc:  # noqa: BLE001 — surface to client during rollout
        return JsonResponse({'error': str(exc)}, status=400)

    result['meta'] = report_run_meta(request)
    try:
        return JsonResponse(result)
    except TypeError:
        return JsonResponse({'error': 'Report output could not be encoded as JSON.'}, status=500)


@_login_required
@require_POST
def master_report_export_excel(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    slug = body.get('report') or ''
    h = get_handler(slug)
    if not h or not hasattr(h, 'run'):
        return JsonResponse({'error': 'Unknown report.'}, status=404)

    payload = {k: v for k, v in body.items() if k != 'report'}
    payload['export'] = True

    try:
        result = h.run(payload)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'error': str(exc)}, status=400)

    title = getattr(h, 'LABEL', slug)

    try:
        if slug == product_attributes.SLUG:
            buf = build_product_attributes_workbook(
                title=title, sections=result.get('sections') or []
            )
        elif slug == product_master.SLUG:
            cols, rows = product_master.flatten_for_export(result)
            buf = build_workbook(title=title, column_defs=cols, rows=rows)
        else:
            h_excel = get_handler(slug)
            flatten = getattr(h_excel, 'flatten_for_export', None)
            if flatten:
                cols, rows = flatten(result)
            else:
                cols, rows = result.get('columns') or [], result.get('rows') or []
            buf = build_workbook(title=title, column_defs=cols, rows=rows)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'error': f'Excel build failed: {exc}'}, status=500)
    fname = f"{slug}_export.xlsx"
    resp = FileResponse(buf, as_attachment=True, filename=fname)
    resp['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return resp


# ─── Transaction reports (config-driven hub, parallel to master reports) ───


@_login_required
def transaction_reports_page(request):
    cat = []
    for meta in transaction_registry.list_reports_meta():
        row = dict(meta)
        row['config_url'] = reverse(
            'transaction_report_config', kwargs={'slug': meta['slug']}
        )
        cat.append(row)
    return render(
        request,
        'reports/transaction_reports.html',
        {
            'reports_catalogue': cat,
            'company_header': getattr(
                settings,
                'REPORT_COMPANY_HEADER',
                COMPANY_NAME_DEFAULT,
            ),
            'api_options_url': reverse('transaction_report_options'),
            'api_data_url': reverse('transaction_report_data'),
            'api_excel_url': reverse('transaction_report_export_excel'),
        },
    )


@_login_required
@require_GET
def transaction_report_config(request, slug):
    h = transaction_registry.get_handler(slug)
    if not h or not hasattr(h, 'get_ui_config'):
        return JsonResponse({'error': 'Unknown report.'}, status=404)
    return JsonResponse(h.get_ui_config())


@_login_required
@require_GET
def transaction_report_options(request):
    slug = request.GET.get('report') or ''
    fk = request.GET.get('filter') or ''
    if slug in _INWARD_REGISTER_SLUGS and fk == 'grn_category':
        return JsonResponse({'options': filter_options_grn_category()})
    if slug == DailyProductionReport.SLUG and fk == 'dpr_section':
        return JsonResponse({'options': filter_options_dpr_section()})
    if slug == InwardGrnReceiptReport.SLUG and fk == 'inward_grn':
        return JsonResponse({'options': filter_options_inward_grn()})
    return JsonResponse({'options': []})


@_login_required
@require_POST
def transaction_report_data(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    slug = body.get('report') or ''
    h = transaction_registry.get_handler(slug)
    if not h or not hasattr(h, 'run'):
        return JsonResponse({'error': 'Unknown report.'}, status=404)

    payload = {k: v for k, v in body.items() if k != 'report'}
    payload['export'] = False

    try:
        result = h.run(payload)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'error': str(exc)}, status=400)

    base_meta = report_run_meta(request)
    handler_meta = result.pop('meta', None)
    if isinstance(handler_meta, dict):
        base_meta = {**base_meta, **handler_meta}
    result['meta'] = base_meta
    try:
        return JsonResponse(result)
    except TypeError:
        return JsonResponse({'error': 'Report output could not be encoded as JSON.'}, status=500)


@_login_required
@require_POST
def transaction_report_export_excel(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    slug = body.get('report') or ''
    h = transaction_registry.get_handler(slug)
    if not h or not hasattr(h, 'run'):
        return JsonResponse({'error': 'Unknown report.'}, status=404)

    payload = {k: v for k, v in body.items() if k != 'report'}
    payload['export'] = True

    try:
        result = h.run(payload)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'error': str(exc)}, status=400)

    title = getattr(h, 'LABEL', slug)

    try:
        flatten = getattr(h, 'flatten_for_export', None)
        if flatten:
            cols, rows = flatten(result)
        else:
            cols, rows = result.get('columns') or [], result.get('rows') or []
        buf = build_workbook(title=title, column_defs=cols, rows=rows)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'error': f'Excel build failed: {exc}'}, status=500)
    fname = f'{slug}_export.xlsx'
    resp = FileResponse(buf, as_attachment=True, filename=fname)
    resp['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return resp
