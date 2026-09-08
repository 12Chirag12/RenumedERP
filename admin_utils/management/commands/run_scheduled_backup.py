from django.core.management.base import BaseCommand, CommandError

from admin_utils.backup_db import BackupError
from admin_utils.backup_schedule import describe_next_backup_wait, maybe_run_scheduled_database_backup
from admin_utils.models import DatabaseBackupSettings


class Command(BaseCommand):
    help = (
        'If periodic backups are enabled in Utilities, run a backup when the day-based interval '
        'has elapsed. Intended for Windows Task Scheduler or cron (e.g. daily or every few hours).'
    )

    def handle(self, *args, **options):
        s = DatabaseBackupSettings.load()
        if not s.schedule_enabled:
            self.stdout.write('Periodic backups are disabled; exiting.')
            return

        try:
            path = maybe_run_scheduled_database_backup()
        except BackupError as e:
            raise CommandError(str(e)) from e
        if path is None:
            msg = describe_next_backup_wait()
            if msg:
                self.stdout.write(f'Next backup not due yet ({msg}).')
            else:
                self.stdout.write('Next backup not due yet.')
            return
        self.stdout.write(self.style.SUCCESS(f'Scheduled backup created: {path}'))
