"""Resolve master report handlers by slug."""

from .handlers import (
    bom_master,
    customer_master,
    item_master,
    machine_master,
    product_attributes,
    product_master,
    supplier_master,
)

MASTER_REPORT_HANDLERS = {
    product_master.SLUG: product_master,
    machine_master.SLUG: machine_master,
    product_attributes.SLUG: product_attributes,
    customer_master.SLUG: customer_master,
    supplier_master.SLUG: supplier_master,
    bom_master.SLUG: bom_master,
    item_master.SLUG: item_master,
}


def get_handler(slug: str):
    return MASTER_REPORT_HANDLERS.get(slug)


def list_reports_meta():
    """Lightweight catalogue for the page dropdown."""
    return [
        {'slug': h.SLUG, 'label': h.LABEL, 'description': getattr(h, 'DESCRIPTION', '')}
        for h in MASTER_REPORT_HANDLERS.values()
    ]
