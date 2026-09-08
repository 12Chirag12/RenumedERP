"""
Background thread: when the app runs under Waitress or django runserver, periodically check
whether a scheduled database backup is due (same rules as ``run_scheduled_backup``).
"""

from __future__ import annotations

import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

_started_lock = threading.Lock()
_started = False


def _scheduler_interval_seconds() -> int:
    raw = getattr(settings, 'DATABASE_BACKUP_SCHEDULER_INTERVAL_SECONDS', 3600)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 3600
    return max(300, min(n, 86400))


def _scheduler_loop() -> None:
    interval = _scheduler_interval_seconds()
    logger.info(
        'Database backup scheduler started (check every %ss; periodic flag in Utilities).',
        interval,
    )
    while True:
        close_old_connections()
        try:
            from admin_utils.backup_schedule import maybe_run_scheduled_database_backup

            path = maybe_run_scheduled_database_backup()
            if path is not None:
                logger.info('Scheduled database backup created: %s', path)
        except Exception:
            logger.exception('Background scheduled database backup failed.')
        finally:
            close_old_connections()
        time.sleep(interval)


def ensure_backup_scheduler_started() -> None:
    """Start at most one daemon thread per process."""
    global _started
    with _started_lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=_scheduler_loop, name='pharmaerp-db-backup', daemon=True)
    t.start()
