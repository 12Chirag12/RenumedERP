"""Compiled patterns and numeric quantizers shared by transaction forms."""

import re
from decimal import Decimal

from ..constants import (
    GRN_NO_PATTERN,
    QTY_DECIMAL_PLACES,
    REGISTER_NO_PATTERN,
    SO_QTY_DECIMAL_PLACES,
)

REGISTER_NO_RE = re.compile(REGISTER_NO_PATTERN)
GRN_NO_RE = re.compile(GRN_NO_PATTERN, re.IGNORECASE)
_QTY_QUANTIZE = Decimal(10) ** -QTY_DECIMAL_PLACES
_SO_QTY_QUANTIZE = Decimal(10) ** -SO_QTY_DECIMAL_PLACES
_BATCH_L_QUANTIZE = Decimal(10) ** -2
_BATCH_N_QUANTIZE = Decimal(10) ** 0
_MONEY_QUANTIZE = Decimal('0.01')
_RM_QTY_QUANTIZE = Decimal(10) ** -QTY_DECIMAL_PLACES

HEADER_DOC_MAX_BYTES = 15 * 1024 * 1024  # 15 MB
HEADER_DOC_EXTENSIONS = ('pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp')
