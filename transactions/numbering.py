"""
Next suggested document serial numbers (register, GRN, sales invoice).

Sequences use the numeric suffix only from values that match canonical
patterns (R-…, RM-… / PM-…, SI-…). Shared GRN counter: RM and PM use one
increasing sequence per financial year.

Autofill pads the suffix to 5 digits for values below 100000 (R-00001 … R-99999);
from 100000 onward the suffix has no fixed width (R-100000, R-100001, …).

Sales invoice numbers (SI-…) use the same padding via compose_document_serial.
"""

from __future__ import annotations

import re

from .models import TrnInwHed, TrnSlsHed

REGISTER_NUM_RE = re.compile(r"^R-(\d+)$", re.IGNORECASE)
GRN_NUM_RE = re.compile(r"^(RM|PM)-(\d+)$", re.IGNORECASE)
INVOICE_NUM_RE = re.compile(r"^SI-(\d+)$", re.IGNORECASE)

# Below this value, suggested numbers use zero-padding to width 5; at/above, plain digits.
_SERIAL_PAD_THRESHOLD = 100_000


def format_serial_suffix(n: int) -> str:
    """R-00001 style below 100000; R-100000 and up without fixed width."""
    if n < _SERIAL_PAD_THRESHOLD:
        return f"{n:05d}"
    return str(n)


def max_register_sequence() -> int:
    best = 0
    for val in TrnInwHed.objects.values_list("register_no", flat=True).iterator():
        if not val:
            continue
        m = REGISTER_NUM_RE.match(str(val).strip())
        if m:
            n = int(m.group(1))
            if n > best:
                best = n
    return best


def max_grn_sequence() -> int:
    best = 0
    for val in TrnInwHed.objects.values_list("grn_no", flat=True).iterator():
        if not val:
            continue
        m = GRN_NUM_RE.match(str(val).strip())
        if m:
            n = int(m.group(2))
            if n > best:
                best = n
    return best


def max_grn_sequence_for_fy(working_year: str) -> int:
    """
    Return the max numeric suffix seen in GRNs for the given working_year (e.g. "2025-26").
    Uses TrnInwHed.working_year to scope sequences per financial year.
    """
    wy = (working_year or "").strip()
    if not wy:
        return 0
    best = 0
    for val in (
        TrnInwHed.objects.filter(working_year=wy)
        .values_list("grn_no", flat=True)
        .iterator()
    ):
        if not val:
            continue
        m = GRN_NUM_RE.match(str(val).strip())
        if m:
            n = int(m.group(2))
            if n > best:
                best = n
    return best


def compose_document_serial(prefix: str, sequence_number: int) -> str:
    """
    Build a document number from a fixed prefix and integer sequence.
    Prefix must include the trailing separator (e.g. 'R-', 'SI-', 'RM-').
    Uses the same suffix padding rules as register no. / GRN (format_serial_suffix).
    """
    p = (prefix or "").strip().upper()
    return f"{p}{format_serial_suffix(int(sequence_number))}"


def suggested_register_no() -> str:
    return compose_document_serial("R-", max_register_sequence() + 1)


def suggested_grn_no(grn_category_id: str, working_year: str) -> str:
    gid = (grn_category_id or "").strip().upper()
    if gid not in ("RM", "PM"):
        return ""
    n = max_grn_sequence_for_fy(working_year) + 1
    return compose_document_serial(f"{gid}-", n)


def max_invoice_sequence_for_fy(working_year: str) -> int:
    """Max numeric suffix of SI-… numbers for the given working_year."""
    wy = (working_year or "").strip()
    if not wy:
        return 0
    best = 0
    for val in (
        TrnSlsHed.objects.filter(working_year=wy)
        .values_list("invoice_no", flat=True)
        .iterator()
    ):
        if not val:
            continue
        m = INVOICE_NUM_RE.match(str(val).strip())
        if m:
            n = int(m.group(1))
            if n > best:
                best = n
    return best


def suggested_sales_invoice_no(working_year: str) -> str:
    return compose_document_serial("SI-", max_invoice_sequence_for_fy(working_year) + 1)
