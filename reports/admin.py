from django.contrib import admin

from .models import ReportAccess


@admin.register(ReportAccess)
class ReportAccessAdmin(admin.ModelAdmin):
    """Assign ``view_master_reports`` to groups or users for finer access control."""

    list_display = ('id',)
