"""
users/management/commands/create_admin.py

Creates the first bootstrap user and assigns the Directors access group.
Django superuser is optional (--django-superuser) for /admin/ only; ERP access is via groups.

    python manage.py sync_access_permissions --apply-presets
    python manage.py create_admin
"""

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from users.models import UserProfile


class Command(BaseCommand):
    help = 'Creates a bootstrap user with the Directors ERP access group.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin', help='Username (default: admin)')
        parser.add_argument('--password', default='Admin@1234', help='Password (default: Admin@1234)')
        parser.add_argument('--email', default='', help='Email (optional)')
        parser.add_argument('--firstname', default='System', help='First name')
        parser.add_argument('--lastname', default='Admin', help='Last name')
        parser.add_argument(
            '--django-superuser',
            action='store_true',
            help='Also grant Django /admin/ superuser (not required for ERP screens).',
        )

    def handle(self, *args, **options):
        username = options['username']

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User "{username}" already exists. Skipping.'))
            return

        directors = Group.objects.filter(name='Directors').first()
        if not directors:
            self.stdout.write(self.style.ERROR(
                'Directors group not found. Run: python manage.py sync_access_permissions --apply-presets'
            ))
            return

        if options['django_superuser']:
            user = User.objects.create_superuser(
                username=username,
                email=options['email'],
                password=options['password'],
                first_name=options['firstname'],
                last_name=options['lastname'],
            )
        else:
            user = User.objects.create_user(
                username=username,
                email=options['email'],
                password=options['password'],
                first_name=options['firstname'],
                last_name=options['lastname'],
            )

        user.groups.add(directors)

        UserProfile.objects.create(
            user=user,
            role='Directors',
            must_change_password=False,
        )

        self.stdout.write(self.style.SUCCESS(
            f'\nBootstrap user created.\n'
            f'  Username : {username}\n'
            f'  Password : {options["password"]}\n'
            f'  ERP access : Directors group\n'
            f'\nChange the password after first login.\n'
        ))
