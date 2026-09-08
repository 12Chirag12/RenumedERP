from django.core.management.base import BaseCommand

from users.access import sync_groups, sync_permissions


class Command(BaseCommand):
    help = 'Sync ERP module permissions and role/department groups from access_registry.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply-presets',
            action='store_true',
            help='Reset group permissions to ROLE_GROUP_PRESETS / DEPARTMENT_GROUP_PRESETS.',
        )

    def handle(self, *args, **options):
        n_perm = sync_permissions()
        n_grp = sync_groups(apply_presets=options['apply_presets'])
        self.stdout.write(
            self.style.SUCCESS(
                f'Synced {n_perm} permissions and {n_grp} groups.'
                + (' Presets applied.' if options['apply_presets'] else '')
            )
        )
