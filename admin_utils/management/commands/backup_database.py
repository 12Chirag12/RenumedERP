from django.core.management.base import BaseCommand, CommandError

from admin_utils.backup_db import BackupError, run_mysql_backup


class Command(BaseCommand):
    help = 'Create a compressed MySQL logical backup (mysqldump) in DATABASE_BACKUP_DIR.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-gzip',
            action='store_true',
            help='Write a plain .sql file instead of .sql.gz.',
        )
        parser.add_argument(
            '--no-track',
            action='store_true',
            help='Do not update last_successful_backup_at / last_error in the database.',
        )

    def handle(self, *args, **options):
        try:
            path = run_mysql_backup(
                gzip_output=not options['no_gzip'],
                track_in_settings=not options['no_track'],
            )
        except BackupError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(self.style.SUCCESS(f'Backup created: {path}'))
