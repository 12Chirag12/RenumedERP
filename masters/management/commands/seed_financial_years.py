"""
Seed MstFinYr with a small default ladder for local/dev.

Run after migrations:

    python manage.py seed_financial_years

Idempotent: updates flags on existing rows to match the intended scenario.
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from masters.models import FinancialYear


# As per IMPLEMENTATION_PROMPT: past closed; 2025-26 current (for Apr 2026); next open.
FY_SEED = [
    {
        'fy_start_year': 2023,
        'fy_end_year': 2024,
        'fy_display': '2023-24',
        'is_current': False,
        'is_open': False,
        'is_closed': True,
    },
    {
        'fy_start_year': 2024,
        'fy_end_year': 2025,
        'fy_display': '2024-25',
        'is_current': False,
        'is_open': True,
        'is_closed': False,
    },
    {
        'fy_start_year': 2025,
        'fy_end_year': 2026,
        'fy_display': '2025-26',
        'is_current': True,
        'is_open': True,
        'is_closed': False,
    },
    {
        'fy_start_year': 2026,
        'fy_end_year': 2027,
        'fy_display': '2026-27',
        'is_current': False,
        'is_open': True,
        'is_closed': False,
    },
]


class Command(BaseCommand):
    help = 'Creates/updates default FinancialYear rows (2023-24 … 2026-27).'

    @transaction.atomic
    def handle(self, *args, **options):
        # Ensure exactly one current after seed: clear others first so clean() passes.
        FinancialYear.objects.update(is_current=False)

        for row in FY_SEED:
            sy = row['fy_start_year']
            ey = row['fy_end_year']
            defaults = {
                'fy_end_year': ey,
                'fy_display': row['fy_display'],
                'start_date': date(sy, 4, 1),
                'end_date': date(ey, 3, 31),
                'is_current': row['is_current'],
                'is_open': row['is_open'],
                'is_closed': row['is_closed'],
            }
            obj, created = FinancialYear.objects.get_or_create(
                fy_start_year=sy,
                defaults=defaults,
            )
            if not created:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'  {action}: {row["fy_display"]}'))

        self.stdout.write(self.style.SUCCESS('Done.'))
