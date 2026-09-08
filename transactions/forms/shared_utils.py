"""
Cross-form helpers (dates, filenames, media).

Do not import form classes here. For helpers whose canonical implementation
lives in ``transactions.numbering`` or ``transactions.utils``, we re-export
them below so form modules can import from this file only (no circular deps).
"""

import os
import re

from django import forms
from django.conf import settings


def _granulation_section_key(section_name: str) -> str | None:
    """Return 'GRANULATION-I' or 'GRANULATION-II' when name matches spec; else None."""
    raw = re.sub(r'\s+', '', ((section_name or '').strip()).upper())
    if raw in ('GRANULATION-I', 'GRANULATION-II'):
        return raw
    return None


def _lubrication_section_key(section_name: str) -> str | None:
    """Return 'LUBRICATION-I' or 'LUBRICATION-II' when name matches spec; else None."""
    raw = re.sub(r'\s+', '', ((section_name or '').strip()).upper())
    if raw in ('LUBRICATION-I', 'LUBRICATION-II'):
        return raw
    return None


def dpr_is_multi_batch_section(section) -> bool:
    """
    DPR sections that use multiple input batch lines (no single log-sheet row on TrnDpr).

    Matches Granulation-I/II and Lubrication-I/II naming (same normalisation as log sheet helpers).
    """
    name = getattr(section, 'section_name', None) or ''
    return _granulation_section_key(name) is not None or _lubrication_section_key(name) is not None


_MMM_YYYY_RE = re.compile(
    r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{4})$',
    re.IGNORECASE,
)

_YYYY_MM_RE = re.compile(r'^(\d{4})-(\d{2})$')

_MMM_TO_MONTH = {
    'JAN': 1,
    'FEB': 2,
    'MAR': 3,
    'APR': 4,
    'MAY': 5,
    'JUN': 6,
    'JUL': 7,
    'AUG': 8,
    'SEP': 9,
    'OCT': 10,
    'NOV': 11,
    'DEC': 12,
}


def _parse_mmm_yyyy(raw, field_label):
    s = (raw or '').strip().upper()
    m = _MMM_YYYY_RE.match(s)
    if not m:
        raise forms.ValidationError(
            f'{field_label} must be in MMM-YYYY format (e.g. JAN-2026).'
        )
    mon_abbr = m.group(1).upper()
    month = _MMM_TO_MONTH.get(mon_abbr)
    if not month:
        raise forms.ValidationError(f'{field_label} has an invalid month.')
    year = int(m.group(2))
    return year, month, s


def _parse_month_any(raw, field_label):
    """
    Accept either:
      - "MMM-YYYY" (JAN-2026), or
      - HTML month input value "YYYY-MM" (2026-01)
    Return (year, month, normalized_mmm_yyyy).
    """
    s = (raw or '').strip()
    if not s:
        raise forms.ValidationError(f'{field_label} is required.')

    mmm = _MMM_YYYY_RE.match(s.strip().upper())
    if mmm:
        y, mo, norm = _parse_mmm_yyyy(s, field_label)
        return y, mo, norm

    ym = _YYYY_MM_RE.match(s)
    if not ym:
        raise forms.ValidationError(
            f'{field_label} must be a valid month (e.g. 2026-01) or MMM-YYYY (e.g. JAN-2026).'
        )
    year = int(ym.group(1))
    month = int(ym.group(2))
    if month < 1 or month > 12:
        raise forms.ValidationError(f'{field_label} has an invalid month.')

    inv = {v: k for k, v in _MMM_TO_MONTH.items()}
    mon = inv.get(month)
    if not mon:
        raise forms.ValidationError(f'{field_label} has an invalid month.')
    norm = f'{mon}-{year}'
    return year, month, norm


def _ym_key(year, month):
    return year * 100 + month


def _normalize_mmm_yyyy(raw):
    _parse_mmm_yyyy(raw, 'Date')
    return (raw or '').strip().upper()


def _delete_media_relative(relative_path):
    if not relative_path:
        return
    full = os.path.join(settings.MEDIA_ROOT, relative_path)
    if os.path.isfile(full):
        os.remove(full)


def _safe_filename_token(s, max_len=80):
    t = re.sub(r'[^\w\-.]', '_', str(s).strip())
    t = re.sub(r'_+', '_', t).strip('_')
    return (t or 'x')[:max_len]


from ..numbering import suggested_register_no  # noqa: E402
from ..utils import validate_transaction_in_open_fy  # noqa: E402
