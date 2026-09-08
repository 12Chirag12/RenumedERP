from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from masters.models import FinancialYear


def get_working_year_for_date(reference_date: date) -> tuple[int, int]:
    """Return (fy_start_year, fy_end_year) for a date in Apr->Mar FY."""
    if not reference_date:
        raise ValueError('reference_date is required')
    if reference_date.month >= 4:
        return reference_date.year, reference_date.year + 1
    return reference_date.year - 1, reference_date.year


def get_working_year_display(fy_start_year: int, fy_end_year: int) -> str:
    """Format as '2025-26'."""
    return f"{int(fy_start_year)}-{str(int(fy_end_year))[-2:]}"


def get_financial_year_from_date(reference_date: date) -> FinancialYear:
    """Lookup & return FinancialYear row for the given date."""
    if not reference_date:
        raise ValueError('reference_date is required')
    fy_start, fy_end = get_working_year_for_date(reference_date)
    return FinancialYear.objects.get(fy_start_year=fy_start, fy_end_year=fy_end)


def get_or_create_financial_year_for_date(reference_date: date) -> FinancialYear:
    """Return FY for a date, creating it if missing."""
    if not reference_date:
        raise ValueError('reference_date is required')
    fy_start, fy_end = get_working_year_for_date(reference_date)
    disp = get_working_year_display(fy_start, fy_end)
    fy, _ = FinancialYear.objects.get_or_create(
        fy_start_year=fy_start,
        defaults={
            'fy_end_year': fy_end,
            'fy_display': disp,
            'start_date': date(fy_start, 4, 1),
            'end_date': date(fy_end, 3, 31),
            'is_current': False,
            'is_open': True,
            'is_closed': False,
        },
    )
    return fy


def get_current_financial_year() -> FinancialYear | None:
    return FinancialYear.objects.filter(is_current=True).first()


def validate_transaction_in_open_fy(transaction_date: date) -> FinancialYear:
    """
    Validate that a FinancialYear exists for transaction_date and that it is open.
    Creates the FY row if missing (same as TrnInwHed.save / admin sync).
    Returns the FY object when valid; raises ValidationError otherwise.
    """
    fy = get_or_create_financial_year_for_date(transaction_date)

    if not fy.is_open or fy.is_closed:
        raise ValidationError(
            f'Financial Year {fy.fy_display} is closed. Cannot add/edit transactions. Contact admin to reopen.'
        )
    return fy


def rollover_financial_year(new_fy_start_year: int) -> FinancialYear:
    """
    Mark the given FY as current+open (and mark any existing current FY as not current).
    """
    with transaction.atomic():
        FinancialYear.objects.filter(is_current=True).update(is_current=False)
        fy = FinancialYear.objects.select_for_update().get(fy_start_year=int(new_fy_start_year))
        fy.is_current = True
        fy.is_open = True
        fy.is_closed = False
        fy.save()
        return fy


def sync_current_financial_year_to_today() -> FinancialYear:
    """
    Ensure that the FY containing today is marked as current+open.
    This is automatic (no manual 'Set current' action in UI).
    """
    today = timezone.localdate()
    fy_today = get_or_create_financial_year_for_date(today)
    return rollover_financial_year(fy_today.fy_start_year)


def enforce_fy_open_close_policy(current_fy: FinancialYear | None = None) -> FinancialYear | None:
    """
    Business rule:
    - Only current FY and the immediately previous FY may be open.
    - All other FYs (older or future) are forced closed.
    - Current FY is always open and not closed.
    - Previous FY: admin may toggle is_open; is_closed mirrors not is_open.
    """
    if current_fy is None:
        current_fy = get_current_financial_year()
    if current_fy is None:
        return None

    current_sy = int(current_fy.fy_start_year)
    prev_sy = current_sy - 1

    with transaction.atomic():
        FinancialYear.objects.filter(fy_start_year=current_sy).update(
            is_current=True,
            is_open=True,
            is_closed=False,
        )

        prev = FinancialYear.objects.filter(fy_start_year=prev_sy).first()
        if prev:
            prev.is_current = False
            prev.is_closed = not bool(prev.is_open)
            prev.save()

        FinancialYear.objects.exclude(fy_start_year__in=[current_sy, prev_sy]).update(
            is_current=False,
            is_open=False,
            is_closed=True,
        )

    return FinancialYear.objects.filter(fy_start_year=current_sy).first()


def validate_fy_closure(fy: FinancialYear) -> None:
    """Raise ValidationError if attempting to close current FY before its end_date."""
    today = timezone.localdate()
    if fy.is_current and fy.end_date and today < fy.end_date:
        raise ValidationError(f'Cannot close current FY before end date ({fy.end_date}).')

