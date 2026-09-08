"""
Shared logic for time-based database backups (Utilities toggle + management command + background thread).
"""

from __future__ import annotations

from pathlib import Path

from django.utils import timezone

from admin_utils.backup_db import BackupError, run_mysql_backup
from admin_utils.models import DatabaseBackupSettings


def maybe_run_scheduled_database_backup() -> Path | None:
    """
    If periodic backups are enabled and the configured day interval has elapsed since the last
    successful backup, run mysqldump. Otherwise no-op.

    Returns the new dump path when a backup was created, or None when skipped.
    """
    s = DatabaseBackupSettings.load()
    if not s.schedule_enabled:
        return None

    now = timezone.now()
    if s.last_successful_backup_at is not None:
        elapsed = (now - s.last_successful_backup_at).total_seconds()
        need = s.interval_days * 86400
        if elapsed < need:
            return None

    return run_mysql_backup()


def describe_next_backup_wait() -> str | None:
    """Human-readable wait until next due backup, or None if disabled / no prior backup."""
    s = DatabaseBackupSettings.load()
    if not s.schedule_enabled:
        return None
    if s.last_successful_backup_at is None:
        return None
    now = timezone.now()
    elapsed = (now - s.last_successful_backup_at).total_seconds()
    need = s.interval_days * 86400
    if elapsed >= need:
        return None
    remaining = int(need - elapsed)
    days_left = remaining // 86400
    hrs_left = (remaining % 86400) // 3600
    return f'~{days_left}d {hrs_left}h remaining at current interval'
