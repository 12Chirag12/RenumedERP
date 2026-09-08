"""
Transactions module constants (shared by forms, views, models, AJAX).
"""

# GRN / inward header: only these MstProdCat.prod_cat_id values are allowed.
GRN_CATEGORY_IDS = ('RM', 'PM')

# Register no. pattern (matches TrnInwHed.register_no validation).
# R- plus one or more digits; autofill uses 5-digit padding until 99999, then 100000+.
REGISTER_NO_PATTERN = r'^R-\d+$'

# GRN no. — RM or PM prefix + digits (shared sequence across types).
GRN_NO_PATTERN = r'^(RM|PM)-\d+$'

# Sales invoice no. (TrnSlsHed.invoice_no) — SI- plus digits, per FY sequence;
# suffix padding matches register/GRN via transactions.numbering.compose_document_serial.
INVOICE_NO_PATTERN = r'^SI-\d+$'

# Decimal places for inward quantities (must match TrnInwDtl1.quantity / TrnInwDtl2.batch_qty).
QTY_DECIMAL_PLACES = 3

# Sales order line / dispatch quantities (TrnSlsOrdDtl1.order_qty, TrnSlsOrdDtl2.disp_qty).
SO_QTY_DECIMAL_PLACES = 2

GST_TYPE_CGST_SGST = 'CGST_SGST'
GST_TYPE_IGST = 'IGST'
GST_TYPE_EXEMPTED = 'EXEMPTED'
GST_TYPE_CHOICES = (
    (GST_TYPE_CGST_SGST, 'CGST + SGST'),
    (GST_TYPE_IGST, 'IGST'),
    (GST_TYPE_EXEMPTED, 'Exempted'),
)
GST_TYPE_IDS = (GST_TYPE_CGST_SGST, GST_TYPE_IGST, GST_TYPE_EXEMPTED)

# FG inventory from DPR: when non-empty, only sections whose name (normalized)
# contains any of these substrings get ``post_dpr_production_to_inventory``.
# Example for Blister / Pouching / Stripping / Bulk Packing:
#   ('BLISTER', 'POUCHING', 'STRIPPING', 'BULKPACKING')
# Empty tuple = all working DPR rows post to InventoryStock (default).
DPR_FG_INVENTORY_SECTION_KEYWORDS: tuple[str, ...] = ()
