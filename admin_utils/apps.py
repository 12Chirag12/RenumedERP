import os
import sys

from django.apps import AppConfig


class AdminUtilsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_utils'
    verbose_name = 'Admin utilities'

    def ready(self) -> None:
        from django.conf import settings

        if not getattr(settings, 'DATABASE_BACKUP_BACKGROUND_SCHEDULER', True):
            return

        web_worker = os.environ.get('PHARMAERP_WEB_WORKER') == '1'
        runserver_child = False
        if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
            runserver_child = os.environ.get('RUN_MAIN') == 'true'

        if not web_worker and not runserver_child:
            return

        from admin_utils.backup_scheduler import ensure_backup_scheduler_started

        ensure_backup_scheduler_started()
