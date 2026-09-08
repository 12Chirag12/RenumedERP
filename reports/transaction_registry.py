"""Resolve transaction report handlers by slug (parallel to master report registry)."""

from .handlers.transactions.inward_raw_material_register import (
    InwardRmRegisterFull,
    InwardRmRegisterStandard,
)
from .handlers.transactions.daily_production_report import DailyProductionReport
from .handlers.transactions.inward_grn_receipt import InwardGrnReceiptReport
from .handlers.transactions.logsheet_report import LogSheetRegisterReport

TRANSACTION_REPORT_HANDLERS = {
    InwardRmRegisterFull.SLUG: InwardRmRegisterFull,
    InwardRmRegisterStandard.SLUG: InwardRmRegisterStandard,
    InwardGrnReceiptReport.SLUG: InwardGrnReceiptReport,
    LogSheetRegisterReport.SLUG: LogSheetRegisterReport,
    DailyProductionReport.SLUG: DailyProductionReport,
    
}


def get_handler(slug: str):
    return TRANSACTION_REPORT_HANDLERS.get(slug)


def list_reports_meta():
    """Catalogue for the transaction reports dropdown (insertion order)."""
    return [
        {'slug': h.SLUG, 'label': h.LABEL, 'description': getattr(h, 'DESCRIPTION', '')}
        for h in TRANSACTION_REPORT_HANDLERS.values()
    ]
