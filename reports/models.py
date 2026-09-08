"""
Legacy anchor model (unused for access). ERP report access uses users.AccessModule
permissions ``reports.master`` and ``reports.transaction`` via Access Control.
"""

from django.db import models


class ReportAccess(models.Model):
    """No business rows required; exists so custom permissions are installable."""

    class Meta:
        verbose_name = 'Report access'
        verbose_name_plural = 'Report access'
        permissions = [
            ('view_master_reports', 'Can view and export master reports'),
        ]
