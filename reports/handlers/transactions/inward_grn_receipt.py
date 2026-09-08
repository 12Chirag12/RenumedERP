"""
Goods Receipt Note — single inward (GRN) document layout for print/preview.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from transactions.models import TrnInwHed

from .inward_raw_material_register import (
    _expand_rows,
    _fmt_dd_mm_yy,
    _fmt_mfg_exp,
    _fmt_qty_val,
    _qty_received_display,
)

SLUG = 'inward_grn_receipt'
LABEL = 'Goods Receipt Note (GRN)'
DESCRIPTION = (
    'Print-style GRN for one inward. Select a GRN from the list. '
    'Manufacturer and financial columns are left blank until captured in the system.'
)

ON_ACCOUNT_OF = 'Renumed Pharmaceutical Labs'
DOC_TITLE = 'Goods Receipt Note'
_OPTION_LIST_LIMIT = 400

# Shown when GRN_RECEIPT_ADDRESS_LINES is not set in settings (matches standard print layout).
_GRN_RECEIPT_DEFAULT_ADDRESS_LINES = [
    'Factory : Plot No. 15, Dewan and Sons Udyog Nagar, Aliyali, Palghar(W), Maharashtra - 401404.',
    'Godown : Plot No. 34, Gala No.2 & 3, Dewan and Sons Udyog Nagar, Aliyali, Palghar(W), Maharashtra - 401404.',
]


def filter_options_inward_grn() -> list[dict[str, Any]]:
    qs = (
        TrnInwHed.objects.select_related('supplier')
        .order_by('-inward_dt', '-inward_id')
        .values('inward_id', 'grn_no', 'register_no', 'inward_dt', 'supplier__supl_name')[
            :_OPTION_LIST_LIMIT
        ]
    )
    out: list[dict[str, Any]] = []
    for r in qs:
        dt = r['inward_dt']
        dt_s = dt.strftime('%d-%m-%Y') if dt else ''
        sup = (r.get('supplier__supl_name') or '').strip()
        grn = (r.get('grn_no') or '').strip()
        reg = (r.get('register_no') or '').strip()
        label = f'{grn} | Reg. {reg} | {dt_s}'
        if sup:
            label += f' — {sup}'
        out.append({'id': r['inward_id'], 'label': label})
    return out


def _load_hed(inward_id: int) -> TrnInwHed | None:
    try:
        return (
            TrnInwHed.objects.select_related(
                'customer',
                'supplier',
                'supplier__state',
                'grn_category',
                'transporter',
                'financial_year',
            )
            .prefetch_related(
                'lines',
                'lines__item',
                'lines__uom',
                'batch_lines',
                'batch_lines__item',
                'batch_lines__product',
            )
            .get(pk=inward_id)
        )
    except TrnInwHed.DoesNotExist:
        return None


def _supplier_address(su) -> str:
    if not su:
        return ''
    parts = [(su.address or '').strip()]
    if su.state_id:
        parts.append((su.state.state_name or '').strip())
    parts.append((su.pin_code or '').strip())
    return ', '.join(p for p in parts if p)


def _receipt_lines(hed: TrnInwHed) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for _h, d1, batch in _expand_rows([hed]):
        item = d1.item
        uom_s = d1.uom.short_name if d1.uom_id else ''
        hsn = (item.hsn_code or '').strip() if item else ''
        desc = (item.item_name or '').strip() if item else ''
        batch_no = (batch.batch_no if batch else '') or ''
        mfg_exp = _fmt_mfg_exp(batch.mfg_dt, batch.exp_dt) if batch else ''
        reval = ''
        ar_no = (batch.arn_no or '').strip() if batch else ''
        qty_pack = _qty_received_display(d1=d1, batch=batch)
        rec_qty_s = ''
        if batch is not None:
            rec_qty_s = f'{_fmt_qty_val(batch.batch_qty)} {uom_s}'.strip()
        else:
            rec_qty_s = f'{_fmt_qty_val(d1.quantity)} {uom_s}'.strip()
        acc_qty_s = rec_qty_s
        rows_out.append(
            {
                'material_code': '',
                'hsn_code': hsn,
                'description': desc,
                'manufacturer': '',
                'batch_no': batch_no,
                'unit': '',
                'mfg_exp': mfg_exp,
                'reval_dt': reval,
                'control_no': '',
                'ar_no': ar_no,
                'storage': '',
                'qty_pack': qty_pack,
                'challan_qty': '',
                'rec_qty': rec_qty_s,
                'rej_qty': '',
                'acc_qty': acc_qty_s,
                'smp_qty': '',
                'rate': '',
                'amount': '',
                'tax': '',
                'tax_pct': '',
                'amount_tax': '',
            }
        )
    return rows_out


def _address_lines_setting() -> list[str]:
    """Factory/Godown lines. If setting is absent, use built-in defaults; if set to [], none shown."""
    raw = getattr(settings, 'GRN_RECEIPT_ADDRESS_LINES', None)
    if raw is not None:
        if isinstance(raw, (list, tuple)):
            return [str(x).strip() for x in raw if str(x).strip()]
        return []
    return list(_GRN_RECEIPT_DEFAULT_ADDRESS_LINES)


def run(payload: dict) -> dict:
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        filters = {}

    raw_id = filters.get('inward_grn')
    if raw_id in (None, ''):
        raise ValueError('Select a GRN to generate the receipt.')
    try:
        inward_id = int(raw_id)
    except (TypeError, ValueError):
        raise ValueError('Invalid GRN selection.')

    hed = _load_hed(inward_id)
    if not hed:
        raise ValueError('Inward not found.')

    su = hed.supplier
    company_name = getattr(settings, 'REPORT_COMPANY_HEADER', '') or 'RENUMED Pharmaceutical Labs.'

    receipt: dict[str, Any] = {
        'document_title': DOC_TITLE,
        'company_name': company_name.strip(),
        'address_lines': _address_lines_setting(),
        'on_account_of': ON_ACCOUNT_OF,
        'supplier_name': (su.supl_name if su else '') or '',
        'supplier_address': _supplier_address(su),
        'supplier_gstin': (su.gst_no or '').strip() if su else '',
        'left_block': {
            'transporter': (
                hed.transporter.transport_name if hed.transporter_id else ''
            ),
            'vehicle_no': (hed.vehicle_no or '').strip(),
            'lr_no': '',
            'lr_date': '',
        },
        'right_block': {
            'grn_type': (
                hed.grn_category.prod_cat_name if hed.grn_category_id else ''
            ),
            'grn_no': (hed.grn_no or '').strip(),
            'register_no': (hed.register_no or '').strip(),
            'format_no': '',
            'po_ref': '',
            'po_date': '',
            'invoice_no': (hed.inv_no or '').strip(),
            'invoice_date': _fmt_dd_mm_yy(hed.inv_dt),
            'challan_no': '',
            'challan_date': '',
            'inward_date': _fmt_dd_mm_yy(hed.inward_dt),
        },
        'lines': _receipt_lines(hed),
        'footer': {
            'exemption': 'NA',
            'sub_total': '',
            'gst_total': '',
            'tcs': '',
            'net_amount': '',
            'complies': '',
        },
    }

    subtitle = f'{receipt["right_block"]["grn_no"]} | Reg. {receipt["right_block"]["register_no"]} | {receipt["right_block"]["inward_date"]}'

    return {
        'layout': 'grn_receipt',
        'receipt': receipt,
        'total_count': len(receipt['lines']),
        'meta': {'report_subtitle': subtitle},
    }


def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
    """Flatten receipt into a simple two-column sheet for Excel."""
    r = result.get('receipt') or {}
    cols = [{'key': 'k', 'label': 'Field'}, {'key': 'v', 'label': 'Value'}]
    rows: list[dict] = []
    rb = r.get('right_block') or {}

    def add(label: str, val: str) -> None:
        rows.append({'k': label, 'v': val or ''})

    add('On A/C of', r.get('on_account_of'))
    add('M/s', r.get('supplier_name'))
    add('Address', r.get('supplier_address'))
    add('GSTIN', r.get('supplier_gstin'))
    add('GRN type', rb.get('grn_type'))
    add('GRN No.', rb.get('grn_no'))
    add('Register No.', rb.get('register_no'))
    add('Inward date', rb.get('inward_date'))
    add('Invoice No.', rb.get('invoice_no'))
    add('Invoice date', rb.get('invoice_date'))
    for i, line in enumerate(r.get('lines') or [], start=1):
        add(f'Line {i} — Description', line.get('description'))
        add(f'Line {i} — Batch', line.get('batch_no'))
        add(f'Line {i} — Rec. qty', line.get('rec_qty'))
    return cols, rows


class InwardGrnReceiptReport:
    SLUG = SLUG
    LABEL = LABEL
    DESCRIPTION = DESCRIPTION

    @staticmethod
    def get_ui_config() -> dict:
        return {
            'slug': SLUG,
            'label': LABEL,
            'print_title': DOC_TITLE,
            'description': DESCRIPTION,
            'layout': 'grn_receipt',
            'hide_excel': True,
            'preview_requires_inward': True,
            'inward_filter_key': 'inward_grn',
            'group_by_options': [],
            'default_group_by': 'none',
            'filters': [
                {
                    'key': 'inward_grn',
                    'label': 'GRN (inward)',
                    'kind': 'inward_grn_select',
                    'placeholder_option': '— Select GRN —',
                },
            ],
            'columns': [],
            'default_columns': [],
            'sortable': [],
            'default_sort': {},
        }

    @staticmethod
    def run(payload: dict) -> dict:
        return run(payload)

    @staticmethod
    def flatten_for_export(result: dict) -> tuple[list[dict], list[dict]]:
        return flatten_for_export(result)
