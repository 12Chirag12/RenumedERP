"""
masters/management/commands/seed_departments.py

Seeds the MstDepartment table with the 6 base departments.
Run once after first migration:

    python manage.py seed_departments

Safe to run multiple times — skips any department that already exists.
"""

from django.core.management.base import BaseCommand
from masters.models import MstDepartment


DEPARTMENTS = [
    "Administration Department",
    "Stores Department",
    "Quality Control (QC) Department",
    "Quality Assurance (QA) Department",
    "Production Department",
    "Packing Department",
    "Dispatch Department",
    "IT Department",
    "Maintenance Department",
]


class Command(BaseCommand):
    help = 'Seeds MstDepartment with the base department list.'

    def handle(self, *args, **options):
        created_count = 0

        for name in DEPARTMENTS:
            obj, created = MstDepartment.objects.get_or_create(dept_name=name)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  ✅ Created: {name}'))
            else:
                self.stdout.write(self.style.WARNING(f'  ⚠️  Already exists: {name}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {created_count} department(s) added.'
        ))