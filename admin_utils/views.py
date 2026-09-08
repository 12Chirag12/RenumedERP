"""
Utilities (financial year, database backup). Access via group permissions (middleware).
"""

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from admin_utils.backup_db import BackupError, delete_backup_file, list_backup_files, resolve_download_path, run_mysql_backup
from admin_utils.models import DatabaseBackupSettings
from masters.models import FinancialYear
from transactions.utils import enforce_fy_open_close_policy, sync_current_financial_year_to_today, validate_fy_closure

def _is_htmx(request) -> bool:
    return (request.headers.get('HX-Request') or '').lower() == 'true'


@login_required
def financial_year_management_view(request):
    current_fy = sync_current_financial_year_to_today()
    current_fy = enforce_fy_open_close_policy(current_fy)

    show_all = (request.GET.get('all') or '').strip() == '1'
    if show_all:
        financial_years = FinancialYear.objects.order_by('-fy_start_year')
    else:
        # Clean UI: only show current + previous by default.
        financial_years = FinancialYear.objects.filter(
            fy_start_year__gte=current_fy.fy_start_year - 1,
        ).order_by('-fy_start_year')

    ctx = {
        'financial_years': financial_years,
        'current_fy': current_fy,
        'show_all': show_all,
        'has_history': FinancialYear.objects.exclude(
            fy_start_year__in=[current_fy.fy_start_year, current_fy.fy_start_year - 1],
        ).exists(),
    }

    if _is_htmx(request):
        return render(request, 'admin_utils/_fy_table.html', ctx)
    return render(
        request,
        'admin_utils/fy_management.html',
        ctx,
    )


@login_required
@require_POST
def toggle_fy_status_api_view(request):
    fy_id = request.POST.get('fy_id')
    action = (request.POST.get('action') or '').strip().lower()
    if fy_id is None or action not in ('close', 'open'):
        return JsonResponse(
            {'success': False, 'error': 'fy_id and action (close|open) are required.'},
            status=400,
        )
    try:
        fy_id = int(fy_id)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid fy_id.'}, status=400)

    current_fy = sync_current_financial_year_to_today()
    current_fy = enforce_fy_open_close_policy(current_fy)

    fy = get_object_or_404(FinancialYear, fy_id=fy_id)
    allowed_years = {int(current_fy.fy_start_year), int(current_fy.fy_start_year) - 1}
    if int(fy.fy_start_year) not in allowed_years:
        return JsonResponse(
            {'success': False, 'error': 'Only current and previous FY can be opened/closed.'},
            status=400,
        )
    inventory_rows_closed = 0
    try:
        if action == 'close':
            validate_fy_closure(fy)
            if fy.is_current:
                return JsonResponse(
                    {'success': False, 'error': 'Current FY cannot be closed.'},
                    status=400,
                )
            fy.is_open = False
            fy.is_closed = True
        else:
            # Only previous FY can be toggled open/close; current is always open.
            if fy.is_current:
                return JsonResponse({'success': True, 'inventory_rows_closed': 0})
            fy.is_open = True
            fy.is_closed = False
        fy.save()
        if action == 'close':
            from inventory.services import close_inventory_stock_opened_in_financial_year

            inventory_rows_closed = close_inventory_stock_opened_in_financial_year(fy)
        enforce_fy_open_close_policy(current_fy)
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': '; '.join(e.messages)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    # HTMX: return refreshed table fragment.
    if _is_htmx(request):
        show_all = (request.POST.get('show_all') or '').strip() == '1'
        if show_all:
            financial_years = FinancialYear.objects.order_by('-fy_start_year')
        else:
            financial_years = FinancialYear.objects.filter(
                fy_start_year__gte=current_fy.fy_start_year - 1,
            ).order_by('-fy_start_year')
        ctx = {
            'financial_years': financial_years,
            'current_fy': FinancialYear.objects.filter(is_current=True).first(),
            'show_all': show_all,
            'has_history': FinancialYear.objects.exclude(
                fy_start_year__in=[current_fy.fy_start_year, current_fy.fy_start_year - 1],
            ).exists(),
        }
        return render(request, 'admin_utils/_fy_table.html', ctx)

    return JsonResponse({'success': True, 'inventory_rows_closed': inventory_rows_closed})


def _database_backup_context(request):
    row = DatabaseBackupSettings.load()
    try:
        files = list_backup_files()
    except BackupError as e:
        files = []
        messages.warning(request, str(e))
    return {
        'backup_settings': row,
        'backup_files': files,
        'backup_dir': str(django_settings.DATABASE_BACKUP_DIR),
        'backup_retention': getattr(django_settings, 'DATABASE_BACKUP_RETENTION', 30),
    }


def _render_database_backup_panel(request, *, show_messages: bool):
    ctx = _database_backup_context(request)
    ctx['show_messages'] = show_messages
    return render(request, 'admin_utils/_backup_panel.html', ctx)


@login_required
def database_backup_view(request):
    ctx = _database_backup_context(request)
    ctx['show_messages'] = False
    return render(request, 'admin_utils/database_backup.html', ctx)


@login_required
@require_POST
def database_backup_run_view(request):
    try:
        path = run_mysql_backup()
        messages.success(request, f'Backup created: {path.name}')
    except BackupError as e:
        messages.error(request, str(e))
    if _is_htmx(request):
        return _render_database_backup_panel(request, show_messages=True)
    return redirect('admin_database_backup')


@login_required
@require_POST
def database_backup_settings_view(request):
    row = DatabaseBackupSettings.load()
    row.schedule_enabled = request.POST.get('schedule_enabled') == 'on'
    try:
        d = int((request.POST.get('interval_days') or '1').strip())
    except (TypeError, ValueError):
        d = 1
    row.interval_days = max(1, min(d, 90))
    row.save(update_fields=['schedule_enabled', 'interval_days'])
    messages.success(request, 'Backup schedule settings saved.')
    if _is_htmx(request):
        return _render_database_backup_panel(request, show_messages=True)
    return redirect('admin_database_backup')


@login_required
@require_POST
def database_backup_delete_view(request):
    name = (request.POST.get('name') or '').strip()
    try:
        delete_backup_file(name)
        messages.success(request, f'Deleted {name}')
    except BackupError as e:
        messages.error(request, str(e))
    if _is_htmx(request):
        return _render_database_backup_panel(request, show_messages=True)
    return redirect('admin_database_backup')


@login_required
def database_backup_download_view(request):
    name = (request.GET.get('f') or '').strip()
    try:
        path = resolve_download_path(name)
    except BackupError:
        raise Http404 from None
    content_type = 'application/gzip' if name.endswith('.gz') else 'application/sql'
    return FileResponse(path.open('rb'), as_attachment=True, filename=name, content_type=content_type)
