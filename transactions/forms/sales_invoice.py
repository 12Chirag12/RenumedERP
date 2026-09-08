"""Sales invoice (TrnSlsHed / TrnSlsDtl1 / TrnSlsDtl2) entry form."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from masters.models import MstCust, MstPkgStyle, MstProd, MstTransport

from inventory.models import InventoryStock
from inventory.transaction_posting import (
    post_sales_invoice_to_inventory,
    reverse_sales_invoice_from_inventory,
)

from ..constants import (
    GST_TYPE_EXEMPTED,
    GST_TYPE_IDS,
    GST_TYPE_IGST,
    INVOICE_NO_PATTERN,
)
from ..models import (
    LOGSHEET_LAYER_SLOT_FIRST,
    LOGSHEET_LAYER_SLOT_SECOND,
    LOGSHEET_LAYER_SLOT_SINGLE,
    TrnBatchDtl,
    TrnLogSheet,
    TrnSlsDtl1,
    TrnSlsDtl2,
    TrnSlsHed,
    TrnSlsOrdDtl1,
    TrnSlsOrdHed,
    logsheet_split_batch_qty,
)
from .shared_utils import validate_transaction_in_open_fy
from ._constants import _MONEY_QUANTIZE, _QTY_QUANTIZE


_INVOICE_NO_RE = re.compile(INVOICE_NO_PATTERN, re.IGNORECASE)


def _line_gst_amounts(taxable: Decimal, gst_per: Decimal, gst_type: str) -> tuple[Decimal, Decimal, Decimal]:
    if gst_type == GST_TYPE_EXEMPTED:
        return Decimal('0'), Decimal('0'), Decimal('0')
    base = (taxable * gst_per / Decimal(100)).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)
    if gst_type == GST_TYPE_IGST:
        return Decimal('0'), Decimal('0'), base
    half = (base / Decimal(2)).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)
    return half, half, Decimal('0')


def _available_fg_lac(customer_id: int, product_id: int, batch_no: str) -> Decimal:
    t = (
        InventoryStock.objects.filter(
            customer_id=customer_id,
            product_id=product_id,
            batch_no=(batch_no or '').strip(),
            item_id__isnull=True,
            is_closed=False,
        ).aggregate(s=Sum('qty'))['s']
    )
    return Decimal(str(t or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)


def _taxable_from_batch_lac(batch_lac: Decimal, pkg_value: int, rate: Decimal) -> Decimal:
    """Same formula as sales order: ((lac * 100000) / packing value) * rate."""
    if batch_lac <= 0 or pkg_value <= 0 or rate <= 0:
        return Decimal('0')
    nos = batch_lac * Decimal('100000')
    packs = (nos / Decimal(pkg_value)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return (packs * rate).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def _logsheet_nominal_qty_l(log_sheet: TrnLogSheet) -> Decimal:
    bl = log_sheet.batch_line
    if not bl:
        return Decimal('0')
    full_l = Decimal(str(bl.batch_qty_l or 0))
    slot = (log_sheet.layer_slot or LOGSHEET_LAYER_SLOT_SINGLE).strip()
    if slot == LOGSHEET_LAYER_SLOT_SINGLE:
        return full_l.quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
    _n1, _n2, l1, l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l)
    if slot == LOGSHEET_LAYER_SLOT_FIRST:
        return l1.quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
    if slot == LOGSHEET_LAYER_SLOT_SECOND:
        return l2.quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
    return full_l.quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)


def _logsheet_invoiced_qty_l(logsheet_id: int, exclude_invoice_id: int | None = None) -> Decimal:
    qs = TrnSlsDtl2.objects.filter(log_sheet_id=logsheet_id)
    if exclude_invoice_id:
        qs = qs.exclude(invoice_line__invoice_id=exclude_invoice_id)
    t = qs.aggregate(s=Sum('batch_qty'))['s']
    return Decimal(str(t or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)


def _logsheet_remaining_qty_l(log_sheet: TrnLogSheet, exclude_invoice_id: int | None = None) -> Decimal:
    nominal = _logsheet_nominal_qty_l(log_sheet)
    invoiced = _logsheet_invoiced_qty_l(log_sheet.pk, exclude_invoice_id=exclude_invoice_id)
    rem = (nominal - invoiced).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
    return rem if rem > 0 else Decimal('0')


def _batch_dtl_invoiced_qty_l(batch_dtl_id: int, exclude_invoice_id: int | None = None) -> Decimal:
    qs = TrnSlsDtl2.objects.filter(log_sheet__batch_line_id=batch_dtl_id)
    if exclude_invoice_id:
        qs = qs.exclude(invoice_line__invoice_id=exclude_invoice_id)
    t = qs.aggregate(s=Sum('batch_qty'))['s']
    return Decimal(str(t or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)


def _batch_dtl_remaining_qty_l(batch_dtl: TrnBatchDtl, exclude_invoice_id: int | None = None) -> Decimal:
    total = Decimal(str(batch_dtl.batch_qty_l or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
    invoiced = _batch_dtl_invoiced_qty_l(batch_dtl.pk, exclude_invoice_id=exclude_invoice_id)
    rem = (total - invoiced).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
    return rem if rem > 0 else Decimal('0')


def _allocate_invoice_qty_to_log_sheets(
    batch_dtl: TrnBatchDtl,
    qty: Decimal,
    *,
    cust_id: int,
    product_id: int,
    ref_order_id: int,
    order_line_id: int,
    exclude_invoice_id: int | None,
    line_idx: int,
    batch_j: int,
) -> list[dict]:
    """Split invoice qty across colour / layer log sheets for one allocated batch line."""
    sheets = list(
        TrnLogSheet.objects.filter(batch_line=batch_dtl)
        .select_related('batch_line', 'batch_line__batch', 'customer', 'product')
        .order_by('layer_slot', 'logsheet_id')
    )
    if not sheets:
        raise forms.ValidationError(
            f'Line {line_idx} batch {batch_j}: batch {batch_dtl.batch_no!r} has no log sheet yet.',
        )
    remaining_qty = qty
    out: list[dict] = []
    for ls in sheets:
        if ls.customer_id != cust_id:
            raise forms.ValidationError(f'Line {line_idx} batch {batch_j}: log sheet customer mismatch.')
        if ls.product_id != product_id:
            raise forms.ValidationError(f'Line {line_idx} batch {batch_j}: log sheet product mismatch.')
        bl = ls.batch_line
        if not bl or not bl.batch:
            raise forms.ValidationError(f'Line {line_idx} batch {batch_j}: log sheet has no batch line.')
        if bl.batch.order_id != ref_order_id:
            raise forms.ValidationError(
                f'Line {line_idx} batch {batch_j}: batch does not belong to the selected sales order.',
            )
        if bl.batch.order_line_id != order_line_id:
            raise forms.ValidationError(f'Line {line_idx} batch {batch_j}: batch does not belong to this order line.')
        rem = _logsheet_remaining_qty_l(ls, exclude_invoice_id=exclude_invoice_id)
        if rem <= 0:
            continue
        take = min(rem, remaining_qty)
        if take > 0:
            out.append({'log_sheet': ls, 'batch_qty': take})
            remaining_qty = (remaining_qty - take).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
    if remaining_qty > 0:
        raise forms.ValidationError(
            f'Line {line_idx} batch {batch_j}: batch qty ({qty}) exceeds remaining to invoice '
            f'for batch {batch_dtl.batch_no!r}.',
        )
    return out


def _order_line_log_sheets(order_line: TrnSlsOrdDtl1):
    return TrnLogSheet.objects.filter(
        batch_line__batch__order_id=order_line.order_id,
        batch_line__batch__order_line_id=order_line.pk,
        product_id=order_line.product_id,
    ).select_related('batch_line')


def refresh_order_line_sale_completed(order_line_id: int) -> None:
    ln = TrnSlsOrdDtl1.objects.select_for_update().get(pk=order_line_id)
    sheets = list(_order_line_log_sheets(ln))
    if not sheets:
        completed = False
    else:
        completed = all(
            _logsheet_remaining_qty_l(ls) <= 0
            for ls in sheets
        )
    if ln.is_sale_completed != completed:
        ln.is_sale_completed = completed
        ln.save(update_fields=['is_sale_completed'])


class SalesInvoiceForm(forms.Form):
    """Sales invoice — header + lines_json (Dtl1 + nested batch rows)."""

    invoice_dt = forms.DateField(
        label='Invoice date',
        error_messages={'required': 'Invoice date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'siInvoiceDt'}),
    )
    invoice_no = forms.CharField(
        max_length=15,
        label='Invoice no.',
        error_messages={'required': 'Invoice no. is required.'},
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'id': 'siInvoiceNo',
            'placeholder': 'SI-00001', 'autocomplete': 'off',
            'spellcheck': 'false',
        }),
    )
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select Customer —',
        error_messages={'required': 'Customer is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'siCustomer'}),
    )
    transporter = forms.ModelChoiceField(
        queryset=MstTransport.objects.none(),
        label='Transporter',
        empty_label='— Select Transporter —',
        error_messages={'required': 'Transporter is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'siTransporter'}),
    )
    reference_order = forms.ModelChoiceField(
        queryset=TrnSlsOrdHed.objects.none(),
        label='Sales order',
        empty_label='— Select sales order —',
        error_messages={'required': 'Sales order is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'siOrderRef'}),
    )
    delivery_add = forms.CharField(
        label='Delivery address',
        error_messages={'required': 'Delivery address is required.'},
        widget=forms.Textarea(attrs={'class': 'cu-textarea', 'id': 'siDeliveryAdd', 'rows': 3}),
    )
    pkg_fwd_amt = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0'),
        label='Packing / forwarding',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'siPkgFwd', 'step': '0.01', 'min': '0'}),
    )
    freight_amt = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0'),
        label='Freight',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'siFreight', 'step': '0.01', 'min': '0'}),
    )
    oth_charges = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0'),
        label='Other charges',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'siOthCharges', 'step': '0.01', 'min': '0'}),
    )
    round_off = forms.DecimalField(
        required=False,
        max_digits=6,
        decimal_places=2,
        initial=Decimal('0'),
        label='Round off',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'siRoundOff', 'step': '0.01', 'min': '-1', 'max': '1'}),
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'cu-textarea', 'id': 'siRemarks', 'rows': 2}),
        label='Remarks',
    )
    lines_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'siLinesJson'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.instance = kwargs.pop('instance', None)
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')
        self.fields['transporter'].queryset = MstTransport.objects.all().order_by('transport_name')
        self.fields['reference_order'].queryset = TrnSlsOrdHed.objects.select_related('customer').order_by(
            '-ord_rec_dt', '-order_id'
        )

    def get_initial(self):
        if not self.instance:
            return {'invoice_dt': timezone.localdate()}
        h = self.instance
        batch_map: dict[int, dict[int, Decimal]] = {}
        for b in TrnSlsDtl2.objects.filter(invoice_line__invoice=h).select_related(
            'invoice_line', 'log_sheet__batch_line',
        ):
            bl_id = b.log_sheet.batch_line_id if b.log_sheet_id else None
            if not bl_id:
                continue
            lid = b.invoice_line_id
            batch_map.setdefault(lid, {})
            batch_map[lid][bl_id] = batch_map[lid].get(bl_id, Decimal('0')) + Decimal(str(b.batch_qty))
        lines = []
        for d1 in h.lines.select_related('product', 'packing_style', 'order_line').order_by('dtl1_id'):
            lines.append({
                'order_line_id': d1.order_line_id,
                'prod_id': d1.product_id,
                'pkg_style_id': d1.packing_style_id,
                'rate': str(d1.rate),
                'gst_type': d1.gst_type,
                'gst_per': str(d1.gst_per),
                'batches': [
                    {'batch_dtl_id': bl_id, 'batch_qty': str(qty)}
                    for bl_id, qty in batch_map.get(d1.pk, {}).items()
                ],
            })
        return {
            'invoice_dt': h.invoice_dt,
            'invoice_no': h.invoice_no,
            'customer': h.customer_id,
            'transporter': h.transporter_id,
            'reference_order': h.reference_order_id,
            'delivery_add': h.delivery_add or '',
            'pkg_fwd_amt': h.pkg_fwd_amt,
            'freight_amt': h.freight_amt,
            'oth_charges': h.oth_charges,
            'round_off': h.round_off,
            'remarks': h.remarks or '',
            'lines_json': json.dumps(lines),
        }

    def clean_invoice_no(self):
        raw = (self.cleaned_data.get('invoice_no') or '').strip().upper()
        if not raw:
            raise forms.ValidationError('Invoice no. is required.')
        if not _INVOICE_NO_RE.match(raw):
            raise forms.ValidationError('Invoice no. must match SI- plus digits (e.g. SI-00001).')
        inv_dt = self.cleaned_data.get('invoice_dt')
        if inv_dt:
            from ..utils import get_or_create_financial_year_for_date

            fy = get_or_create_financial_year_for_date(inv_dt)
            qs = TrnSlsHed.objects.filter(invoice_no=raw, financial_year=fy)
            if self.instance and getattr(self.instance, 'pk', None):
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f'Invoice no. "{raw}" already exists for this financial year.')
        return raw

    def clean_reference_order(self):
        ro = self.cleaned_data.get('reference_order')
        if not ro:
            raise forms.ValidationError('Sales order is required.')
        cust = self.cleaned_data.get('customer')
        if cust and ro.customer_id != cust.pk:
            raise forms.ValidationError('Sales order must belong to the selected customer.')
        return ro

    def _nonneg_money(self, field_name, label):
        raw = self.cleaned_data.get(field_name)
        if raw is None:
            return Decimal('0')
        v = Decimal(str(raw)).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)
        if v < 0:
            raise forms.ValidationError(f'{label} must be zero or greater.')
        return v

    def clean_pkg_fwd_amt(self):
        return self._nonneg_money('pkg_fwd_amt', 'Packing / forwarding')

    def clean_freight_amt(self):
        return self._nonneg_money('freight_amt', 'Freight')

    def clean_oth_charges(self):
        return self._nonneg_money('oth_charges', 'Other charges')

    def clean_round_off(self):
        raw = self.cleaned_data.get('round_off')
        if raw is None:
            return Decimal('0')
        v = Decimal(str(raw)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if v < -1 or v > 1:
            raise forms.ValidationError('Round off must be between -1 and 1.')
        return v

    def clean_lines_json(self):
        raw = (self.cleaned_data.get('lines_json') or '').strip()
        inv_dt = self.cleaned_data.get('invoice_dt')
        cust = self.cleaned_data.get('customer')
        ref_order = self.cleaned_data.get('reference_order')
        if not inv_dt:
            raise forms.ValidationError('Enter invoice date before adding product lines.')
        if not cust:
            raise forms.ValidationError('Select customer before adding product lines.')
        if not ref_order:
            raise forms.ValidationError('Select sales order before adding product lines.')
        if not raw or raw == '[]':
            raise forms.ValidationError('Add at least one product line.')
        try:
            rows = json.loads(raw)
        except ValueError:
            raise forms.ValidationError('Invalid line data.')
        if not isinstance(rows, list):
            raise forms.ValidationError('Invalid line format.')

        exclude_inv_id = self.instance.pk if self.instance else None
        seen_order_lines = set()
        validated = []

        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f'Line {idx}: invalid row.')

            ol_raw = row.get('order_line_id')
            prod_id = row.get('prod_id')
            rate_raw = row.get('rate')
            gst_type = (row.get('gst_type') or '').strip()
            gst_per_raw = row.get('gst_per')
            batches_raw = row.get('batches') or []

            if not ol_raw:
                raise forms.ValidationError(f'Line {idx}: sales order line is required.')
            try:
                order_line = TrnSlsOrdDtl1.objects.select_related(
                    'product', 'packing_style', 'order',
                ).get(pk=int(ol_raw), order_id=ref_order.pk)
            except (TrnSlsOrdDtl1.DoesNotExist, TypeError, ValueError):
                raise forms.ValidationError(f'Line {idx}: invalid sales order line.')

            if order_line.is_sale_completed:
                raise forms.ValidationError(f'Line {idx}: this product is already fully invoiced on the order.')

            product = order_line.product
            packing = order_line.packing_style
            if prod_id and int(prod_id) != product.pk:
                raise forms.ValidationError(f'Line {idx}: product does not match the sales order line.')

            if order_line.order.customer_id != cust.pk:
                raise forms.ValidationError(f'Line {idx}: sales order line customer mismatch.')

            if gst_type not in GST_TYPE_IDS:
                raise forms.ValidationError(f'Line {idx}: invalid GST type.')

            try:
                gst_per = Decimal(str(gst_per_raw))
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Line {idx}: GST % must be a number.')
            gst_per = gst_per.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if gst_per < 0 or gst_per > 100:
                raise forms.ValidationError(f'Line {idx}: GST % must be between 0 and 100.')

            try:
                rate = Decimal(str(rate_raw))
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Line {idx}: rate must be a number.')
            rate = rate.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
            if rate <= 0:
                raise forms.ValidationError(f'Line {idx}: rate must be greater than zero.')

            if order_line.pk in seen_order_lines:
                raise forms.ValidationError(f'Line {idx}: duplicate product on this invoice.')
            seen_order_lines.add(order_line.pk)

            if not isinstance(batches_raw, list) or not batches_raw:
                raise forms.ValidationError(f'Line {idx}: add at least one batch allocation.')

            pkg_val = int(packing.pkg_style_value or 0)
            if pkg_val <= 0:
                raise forms.ValidationError(f'Line {idx}: packing style value is invalid.')

            batch_sum = Decimal('0')
            seen_batch_dtl: set[int] = set()
            seen_ls: set[int] = set()
            batches_parsed = []
            for j, br in enumerate(batches_raw, start=1):
                if not isinstance(br, dict):
                    raise forms.ValidationError(f'Line {idx} batch {j}: invalid data.')
                dtl_raw = br.get('batch_dtl_id')
                ls_raw = br.get('logsheet_id')
                bq_raw = br.get('batch_qty')
                try:
                    bq = Decimal(str(bq_raw))
                except (InvalidOperation, TypeError):
                    raise forms.ValidationError(f'Line {idx} batch {j}: batch qty must be a number.')
                bq = bq.quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                if bq <= 0:
                    raise forms.ValidationError(f'Line {idx} batch {j}: batch qty must be greater than zero.')

                if dtl_raw not in (None, ''):
                    try:
                        dtl_id = int(dtl_raw)
                    except (TypeError, ValueError):
                        raise forms.ValidationError(f'Line {idx} batch {j}: invalid allocated batch.')
                    if dtl_id in seen_batch_dtl:
                        raise forms.ValidationError(f'Line {idx}: duplicate allocated batch in batch rows.')
                    seen_batch_dtl.add(dtl_id)
                    try:
                        batch_dtl = TrnBatchDtl.objects.select_related('batch').get(pk=dtl_id)
                    except TrnBatchDtl.DoesNotExist:
                        raise forms.ValidationError(f'Line {idx} batch {j}: allocated batch not found.')
                    bh = batch_dtl.batch
                    if not bh:
                        raise forms.ValidationError(f'Line {idx} batch {j}: allocated batch has no header.')
                    if bh.order_id != ref_order.pk:
                        raise forms.ValidationError(
                            f'Line {idx} batch {j}: batch does not belong to the selected sales order.',
                        )
                    if bh.order_line_id != order_line.pk:
                        raise forms.ValidationError(
                            f'Line {idx} batch {j}: batch does not belong to this order line.',
                        )
                    if bh.product_id != product.pk:
                        raise forms.ValidationError(f'Line {idx} batch {j}: batch product mismatch.')

                    remain = _batch_dtl_remaining_qty_l(batch_dtl, exclude_invoice_id=exclude_inv_id)
                    if self.instance:
                        prev_same = TrnSlsDtl2.objects.filter(
                            log_sheet__batch_line_id=dtl_id,
                            invoice_line__invoice=self.instance,
                        ).aggregate(s=Sum('batch_qty'))['s']
                        prev_amt = Decimal(str(prev_same or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                        remain = (remain + prev_amt).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                    if bq > remain:
                        raise forms.ValidationError(
                            f'Line {idx} batch {j}: batch qty ({bq}) exceeds remaining to invoice ({remain}) '
                            f'for batch {batch_dtl.batch_no!r}.',
                        )

                    avail = _available_fg_lac(cust.pk, product.pk, batch_dtl.batch_no)
                    if self.instance:
                        prev_same = TrnSlsDtl2.objects.filter(
                            log_sheet__batch_line_id=dtl_id,
                            invoice_line__invoice=self.instance,
                        ).aggregate(s=Sum('batch_qty'))['s']
                        prev_amt = Decimal(str(prev_same or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                        avail = (avail + prev_amt).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                    if bq > avail:
                        raise forms.ValidationError(
                            f'Line {idx} batch {j}: batch qty ({bq}) exceeds available stock ({avail}) '
                            f'for batch {batch_dtl.batch_no!r}.',
                        )

                    allocations = _allocate_invoice_qty_to_log_sheets(
                        batch_dtl,
                        bq,
                        cust_id=cust.pk,
                        product_id=product.pk,
                        ref_order_id=ref_order.pk,
                        order_line_id=order_line.pk,
                        exclude_invoice_id=exclude_inv_id,
                        line_idx=idx,
                        batch_j=j,
                    )
                    batch_sum += bq
                    batches_parsed.extend(allocations)
                    continue

                if ls_raw in (None, ''):
                    raise forms.ValidationError(f'Line {idx} batch {j}: select an allocated batch.')

                try:
                    ls_id = int(ls_raw)
                except (TypeError, ValueError):
                    raise forms.ValidationError(f'Line {idx} batch {j}: invalid log sheet.')
                if ls_id in seen_ls:
                    raise forms.ValidationError(f'Line {idx}: duplicate log sheet in batch rows.')
                seen_ls.add(ls_id)
                try:
                    log_sheet = TrnLogSheet.objects.select_related(
                        'batch_line', 'batch_line__batch', 'customer', 'product',
                    ).get(pk=ls_id)
                except TrnLogSheet.DoesNotExist:
                    raise forms.ValidationError(f'Line {idx} batch {j}: log sheet not found.')
                if log_sheet.customer_id != cust.pk:
                    raise forms.ValidationError(f'Line {idx} batch {j}: log sheet customer mismatch.')
                if log_sheet.product_id != product.pk:
                    raise forms.ValidationError(f'Line {idx} batch {j}: log sheet product mismatch.')
                bl = log_sheet.batch_line
                if not bl or not bl.batch:
                    raise forms.ValidationError(f'Line {idx} batch {j}: log sheet has no batch line.')
                if bl.batch.order_id != ref_order.pk:
                    raise forms.ValidationError(f'Line {idx} batch {j}: batch does not belong to the selected sales order.')
                if bl.batch.order_line_id != order_line.pk:
                    raise forms.ValidationError(f'Line {idx} batch {j}: batch does not belong to this order line.')
                remain_ls = _logsheet_remaining_qty_l(log_sheet, exclude_invoice_id=exclude_inv_id)
                if self.instance:
                    prev_same = TrnSlsDtl2.objects.filter(
                        log_sheet_id=log_sheet.pk,
                        invoice_line__invoice=self.instance,
                    ).aggregate(s=Sum('batch_qty'))['s']
                    prev_amt = Decimal(str(prev_same or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                    remain_ls = (remain_ls + prev_amt).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                if bq > remain_ls:
                    raise forms.ValidationError(
                        f'Line {idx} batch {j}: batch qty ({bq}) exceeds remaining to invoice ({remain_ls}) '
                        f'for batch {bl.batch_no!r}.',
                    )

                avail = _available_fg_lac(cust.pk, product.pk, bl.batch_no)
                if self.instance:
                    prev_same = TrnSlsDtl2.objects.filter(
                        log_sheet_id=log_sheet.pk,
                        invoice_line__invoice=self.instance,
                    ).aggregate(s=Sum('batch_qty'))['s']
                    prev_amt = Decimal(str(prev_same or 0)).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                    avail = (avail + prev_amt).quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                if bq > avail:
                    raise forms.ValidationError(
                        f'Line {idx} batch {j}: batch qty ({bq}) exceeds available stock ({avail}) '
                        f'for batch {bl.batch_no!r}.',
                    )

                batch_sum += bq
                batches_parsed.append({'log_sheet': log_sheet, 'batch_qty': bq})

            batch_sum = batch_sum.quantize(_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
            quantity = batch_sum
            taxable = _taxable_from_batch_lac(quantity, pkg_val, rate)
            cgst, sgst, igst = _line_gst_amounts(taxable, gst_per, gst_type)
            prod_amt = (taxable + cgst + sgst + igst).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)

            validated.append({
                'order_line': order_line,
                'product': product,
                'packing_style': packing,
                'quantity': quantity,
                'rate': rate,
                'taxable_amt': taxable,
                'gst_type': gst_type,
                'gst_per': gst_per,
                'cgst_amt': cgst,
                'sgst_amt': sgst,
                'igst_amt': igst,
                'prod_amt': prod_amt,
                'batches': batches_parsed,
            })

        return validated

    def clean(self):
        cd = super().clean()
        inv_dt = cd.get('invoice_dt')
        if inv_dt:
            try:
                validate_transaction_in_open_fy(inv_dt)
            except ValidationError as e:
                raise forms.ValidationError(e.messages)
            from ..utils import get_or_create_financial_year_for_date

            fy = get_or_create_financial_year_for_date(inv_dt)
            if inv_dt < fy.start_date or inv_dt > fy.end_date:
                self.add_error('invoice_dt', 'Invoice date must fall within the financial year.')
        return cd

    def save(self) -> TrnSlsHed:
        cd = self.cleaned_data
        lines = cd['lines_json']
        user = self.user if getattr(self.user, 'pk', None) else None

        taxable_sum = sum((ln['taxable_amt'] for ln in lines), Decimal('0'))
        cgst_sum = sum((ln['cgst_amt'] for ln in lines), Decimal('0'))
        sgst_sum = sum((ln['sgst_amt'] for ln in lines), Decimal('0'))
        igst_sum = sum((ln['igst_amt'] for ln in lines), Decimal('0'))

        pkg = cd['pkg_fwd_amt']
        frt = cd['freight_amt']
        oth = cd['oth_charges']
        rnd = cd['round_off']
        total = (
            taxable_sum + pkg + frt + oth + cgst_sum + sgst_sum + igst_sum + rnd
        ).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)

        affected_order_lines: set[int] = set()
        try:
            with db_transaction.atomic():
                if self.instance:
                    reverse_sales_invoice_from_inventory(self.instance)
                    for old in TrnSlsDtl1.objects.filter(invoice=self.instance).only('order_line_id'):
                        if old.order_line_id:
                            affected_order_lines.add(old.order_line_id)
                    TrnSlsDtl2.objects.filter(invoice_line__invoice=self.instance).delete()
                    TrnSlsDtl1.objects.filter(invoice=self.instance).delete()
                    hed = self.instance
                    hed.invoice_no = cd['invoice_no']
                    hed.invoice_dt = cd['invoice_dt']
                    hed.customer = cd['customer']
                    hed.transporter = cd['transporter']
                    hed.reference_order = cd.get('reference_order')
                    hed.delivery_add = (cd.get('delivery_add') or '').strip()
                    hed.pkg_fwd_amt = pkg
                    hed.freight_amt = frt
                    hed.oth_charges = oth
                    hed.round_off = rnd
                    hed.taxable_val = taxable_sum
                    hed.cgst_amt = cgst_sum
                    hed.sgst_amt = sgst_sum
                    hed.igst_amt = igst_sum
                    hed.total_amt = total
                    hed.remarks = (cd.get('remarks') or '').strip() or None
                    hed.updated_by = user
                    hed.save()
                else:
                    hed = TrnSlsHed(
                        invoice_no=cd['invoice_no'],
                        invoice_dt=cd['invoice_dt'],
                        customer=cd['customer'],
                        transporter=cd['transporter'],
                        reference_order=cd.get('reference_order'),
                        delivery_add=(cd.get('delivery_add') or '').strip(),
                        pkg_fwd_amt=pkg,
                        freight_amt=frt,
                        oth_charges=oth,
                        round_off=rnd,
                        taxable_val=taxable_sum,
                        cgst_amt=cgst_sum,
                        sgst_amt=sgst_sum,
                        igst_amt=igst_sum,
                        total_amt=total,
                        remarks=(cd.get('remarks') or '').strip() or None,
                        created_by=user,
                        updated_by=user,
                    )
                    hed.save()

                for ln in lines:
                    d1 = TrnSlsDtl1(
                        invoice=hed,
                        order_line=ln['order_line'],
                        product=ln['product'],
                        packing_style=ln['packing_style'],
                        quantity=ln['quantity'],
                        rate=ln['rate'],
                        taxable_amt=ln['taxable_amt'],
                        gst_type=ln['gst_type'],
                        gst_per=ln['gst_per'],
                        cgst_amt=ln['cgst_amt'],
                        sgst_amt=ln['sgst_amt'],
                        igst_amt=ln['igst_amt'],
                        prod_amt=ln['prod_amt'],
                    )
                    d1.save()
                    if ln['order_line']:
                        affected_order_lines.add(ln['order_line'].pk)
                    for br in ln['batches']:
                        TrnSlsDtl2(
                            invoice_line=d1,
                            log_sheet=br['log_sheet'],
                            batch_qty=br['batch_qty'],
                        ).save()

                post_sales_invoice_to_inventory(hed)
                for ol_id in affected_order_lines:
                    refresh_order_line_sale_completed(ol_id)
                return hed
        except IntegrityError:
            raise forms.ValidationError(
                'Could not save: duplicate invoice number or a database constraint failed.',
            ) from None
