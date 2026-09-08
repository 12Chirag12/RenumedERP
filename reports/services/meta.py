"""Shared metadata for preview and exports."""

from django.utils import timezone

# Default print header when REPORT_COMPANY_HEADER is not set in Django settings.
COMPANY_NAME_DEFAULT = 'RENUMED Pharmaceutical Labs.'


def report_run_meta(request):
    user = request.user
    name = user.get_full_name().strip() if user.get_full_name() else user.username
    return {
        'generated_at': timezone.localtime(timezone.now()).isoformat(),
        'generated_at_display': timezone.localtime(timezone.now()).strftime('%d-%b-%Y %H:%M'),
        'user_username': user.username,
        'user_display': name,
    }
