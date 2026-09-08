"""
transactions/forms.py

Inward (GRN) — implements the same two-method contract as masters/forms.py:

    get_initial(self) -> dict
        Pre-fill for GET. Returns {} when self.instance is None except default
        inward date for new records (via get_initial used by the view).

    save(self) -> model instance
        Called after is_valid(). Creates TrnInwHed + detail rows in one atomic
        transaction. Raises ValidationError on IntegrityError or when edit is
        requested but not implemented.
"""

import json
import os
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import IntegrityError, models
from django.db import transaction as db_transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from masters.models import (
    MstCust,
    MstCustProd,
    MstItem,
    MstMachine,
    MstPkgStyle,
    MstProd,
    MstProdCat,
    MstSection,
    MstSupplier,
    MstTransport,
    MstBomRmHed,
    MstBomRmDtl,
)

from .constants import (
    GRN_CATEGORY_IDS,
    GRN_NO_PATTERN,
    GST_TYPE_EXEMPTED,
    GST_TYPE_IGST,
    GST_TYPE_IDS,
    QTY_DECIMAL_PLACES,
    REGISTER_NO_PATTERN,
    SO_QTY_DECIMAL_PLACES,
)
from .models import (
    LOGSHEET_LAYER_SLOT_CHOICES,
    LOGSHEET_LAYER_SLOT_FIRST,
    LOGSHEET_LAYER_SLOT_SECOND,
    LOGSHEET_LAYER_SLOT_SINGLE,
    LOGSHEET_SHIFT_CHOICES,
    TrnBatchDtl,
    TrnBatchHed,
    TrnInwDtl1,
    TrnInwDtl2,
    TrnInwHed,
    TrnLogSheet,
    TrnSlsOrdDtl1,
    TrnSlsOrdDtl2,
    TrnSlsOrdHed,
    TrnlssDtl,
    TrnlssHed,
    logsheet_split_batch_qty,
)
from .numbering import suggested_register_no
from .utils import validate_transaction_in_open_fy


def _granulation_section_key(section_name: str) -> str | None:
    """Return 'GRANULATION-I' or 'GRANULATION-II' when name matches spec; else None."""
    raw = re.sub(r'\s+', '', ((section_name or '').strip()).upper())
    if raw in ('GRANULATION-I', 'GRANULATION-II'):
        return raw
    return None

REGISTER_NO_RE = re.compile(REGISTER_NO_PATTERN)
GRN_NO_RE = re.compile(GRN_NO_PATTERN, re.IGNORECASE)
_QTY_QUANTIZE = Decimal(10) ** -QTY_DECIMAL_PLACES
_SO_QTY_QUANTIZE = Decimal(10) ** -SO_QTY_DECIMAL_PLACES
_BATCH_L_QUANTIZE = Decimal(10) ** -2
_BATCH_N_QUANTIZE = Decimal(10) ** 0
_MONEY_QUANTIZE = Decimal('0.01')

_MMM_YYYY_RE = re.compile(
    r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{4})$',
    re.IGNORECASE,
)

_YYYY_MM_RE = re.compile(r'^(\d{4})-(\d{2})$')


_MMM_TO_MONTH = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
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

HEADER_DOC_MAX_BYTES = 15 * 1024 * 1024  # 15 MB
HEADER_DOC_EXTENSIONS = ('pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp')


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


def _inward_document_filename(register_no, supplier_name, inward_dt, original_name):
    ext = os.path.splitext(original_name or '')[1].lower()
    if ext not in ('.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'):
        ext = '.pdf'
    date_s = inward_dt.isoformat() if hasattr(inward_dt, 'isoformat') else str(inward_dt)
    base = '_'.join(
        _safe_filename_token(x)
        for x in (register_no, supplier_name, date_s)
    )
    return base + ext


def _save_inward_header_file(uploaded, register_no, supplier, inward_dt):
    """Write to MEDIA_ROOT/inward_documents/; return relative path."""
    subdir = 'inward_documents'
    upload_dir = os.path.join(settings.MEDIA_ROOT, subdir)
    os.makedirs(upload_dir, exist_ok=True)
    name = _inward_document_filename(
        register_no,
        supplier.supl_name if supplier else '',
        inward_dt,
        getattr(uploaded, 'name', '') or '',
    )
    dest_rel = f'{subdir}/{name}'
    dest_abs = os.path.join(settings.MEDIA_ROOT, dest_rel)
    with open(dest_abs, 'wb+') as fh:
        for chunk in uploaded.chunks():
            fh.write(chunk)
    return dest_rel


def _sales_order_document_filename(customer_name, ord_rec_dt, original_name):
    ext = os.path.splitext(original_name or '')[1].lower()
    if ext not in ('.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'):
        ext = '.pdf'
    date_s = ord_rec_dt.isoformat() if hasattr(ord_rec_dt, 'isoformat') else str(ord_rec_dt)
    base = '_'.join(
        _safe_filename_token(x)
        for x in (customer_name, date_s)
    )
    return base + ext


def _save_sales_order_header_file(uploaded, customer, ord_rec_dt):
    """Write to MEDIA_ROOT/sales_order_documents/; return relative path (≤150 chars best-effort)."""
    subdir = 'sales_order_documents'
    upload_dir = os.path.join(settings.MEDIA_ROOT, subdir)
    os.makedirs(upload_dir, exist_ok=True)
    name = _sales_order_document_filename(
        customer.cust_name if customer else '',
        ord_rec_dt,
        getattr(uploaded, 'name', '') or '',
    )
    dest_rel = f'{subdir}/{name}'
    dest_abs = os.path.join(settings.MEDIA_ROOT, dest_rel)
    with open(dest_abs, 'wb+') as fh:
        for chunk in uploaded.chunks():
            fh.write(chunk)
    return dest_rel


def _line_gst_amounts(taxable: Decimal, gst_per: Decimal, gst_type: str) -> tuple[Decimal, Decimal, Decimal]:
    """Return (cgst, sgst, igst) per GST type rules."""
    if gst_type == GST_TYPE_EXEMPTED:
        return Decimal('0'), Decimal('0'), Decimal('0')
    base = (taxable * gst_per / Decimal(100)).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)
    if gst_type == GST_TYPE_IGST:
        return Decimal('0'), Decimal('0'), base
    half = (base / Decimal(2)).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)
    return half, half, Decimal('0')


def _parse_optional_date(raw, line_idx, bidx, label):
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    d = raw if hasattr(raw, 'year') else parse_date(str(raw).strip())
    if not d:
        raise forms.ValidationError(
            f'Line {line_idx} batch {bidx}: invalid {label}.'
        )
    return d


class InwardForm(forms.Form):
    inward_dt = forms.DateField(
        label='Inward Date',
        error_messages={'required': 'Inward date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'inwInwardDt'}),
    )
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select Customer —',
        error_messages={'required': 'Customer is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'inwCustomer'}),
    )
    register_no = forms.CharField(
        max_length=20,
        label='Register No.',
        error_messages={'required': 'Register no. is required.'},
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'id': 'inwRegisterNo',
            'placeholder': 'R-00001', 'autocomplete': 'off',
            'inputmode': 'numeric',
            'spellcheck': 'false',
        }),
    )
    grn_category = forms.ModelChoiceField(
        queryset=MstProdCat.objects.none(),
        label='GRN Type',
        empty_label='— RM / PM —',
        error_messages={'required': 'GRN type is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'inwGrnCategory'}),
    )
    grn_no = forms.CharField(
        max_length=50,
        label='GRN No.',
        error_messages={'required': 'GRN no. is required.'},
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'id': 'inwGrnNo',
            'placeholder': 'RM-00001', 'autocomplete': 'off',
            'inputmode': 'numeric',
            'spellcheck': 'false',
        }),
    )
    supplier = forms.ModelChoiceField(
        queryset=MstSupplier.objects.none(),
        label='Supplier',
        empty_label='— Select Supplier —',
        error_messages={'required': 'Supplier is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'inwSupplier'}),
    )
    inv_no = forms.CharField(
        max_length=100,
        label='Invoice No.',
        error_messages={'required': 'Invoice no. is required.'},
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'inwInvNo', 'autocomplete': 'off'}),
    )
    inv_dt = forms.DateField(
        label='Invoice Date',
        error_messages={'required': 'Invoice date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'inwInvDt'}),
    )
    transporter = forms.ModelChoiceField(
        queryset=MstTransport.objects.none(),
        label='Transporter',
        empty_label='— Select Transporter —',
        error_messages={'required': 'Transporter is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'inwTransport'}),
    )
    vehicle_no = forms.CharField(
        required=False,
        max_length=50,
        label='Vehicle No.',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'inwVehicle', 'autocomplete': 'off'}),
    )
    driver_name = forms.CharField(
        required=False,
        max_length=150,
        label='Driver Name',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'inwDriverName', 'autocomplete': 'off'}),
    )
    driver_no = forms.CharField(
        required=False,
        max_length=10,
        label='Driver Contact',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '10-digit contact',
            'id': 'inwDriverNo', 'autocomplete': 'tel-national', 'maxlength': '10',
        }),
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'cu-textarea', 'id': 'inwRemarks', 'rows': 2,
            'placeholder': 'Optional notes…',
        }),
        label='Remarks',
    )
    lines_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'inwLinesJson'}),
    )
    header_document = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(list(HEADER_DOC_EXTENSIONS))],
        widget=forms.FileInput(attrs={
            'class': 'inw-header-doc-input',
            'id': 'inwHeaderDocInput',
            'accept': '.pdf,image/*',
        }),
        label='Document',
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')
        self.fields['supplier'].queryset = MstSupplier.objects.all().order_by('supl_name')
        self.fields['transporter'].queryset = MstTransport.objects.all().order_by('transport_name')
        self.fields['grn_category'].queryset = MstProdCat.objects.filter(
            prod_cat_id__in=GRN_CATEGORY_IDS,
        ).order_by('prod_cat_name')

    def get_initial(self):
        if not self.instance:
            return {
                'inward_dt': timezone.localdate(),
                'register_no': suggested_register_no(),
            }
        h = self.instance

        # Build lines_json from TrnInwDtl1 + TrnInwDtl2 so the JS wizard
        # can hydrate step-2 when the user opens an existing record for edit.
        # One pass over batch lines (TrnInwDtl2), grouped by item, preserves order
        # and keeps header + line + batch data in sync.
        batch_map = defaultdict(list)
        # Use .all() so prefetched batch_lines from the view (ordered by dtl2_id) are used in one shot.
        for d2 in h.batch_lines.all():
            batch_map[d2.item_id].append({
                'batch_no': d2.batch_no,
                'arn_no': d2.arn_no or '',
                'pack_style': d2.pack_style,
                'mfg_dt': str(d2.mfg_dt) if d2.mfg_dt else '',
                'exp_dt': str(d2.exp_dt) if d2.exp_dt else '',
                'batch_qty': str(d2.batch_qty),
                'prod_id': d2.product_id or '',
            })

        lines = []
        for d1 in h.lines.all():
            lines.append({
                'item_id': d1.item_id,
                'qty': str(d1.quantity),
                'batches': batch_map.get(d1.item_id, []),
            })

        return {
            'inward_dt': h.inward_dt,
            'customer': h.customer_id,
            'register_no': h.register_no,
            'grn_category': h.grn_category_id,
            'grn_no': h.grn_no,
            'supplier': h.supplier_id,
            'inv_no': h.inv_no,
            'inv_dt': h.inv_dt,
            'transporter': h.transporter_id,
            'vehicle_no': h.vehicle_no or '',
            'driver_name': h.driver_name or '',
            'driver_no': h.driver_no or '',
            'remarks': h.remarks or '',
            'lines_json': json.dumps(lines),
        }

    def clean_header_document(self):
        f = self.cleaned_data.get('header_document')
        if not f or not getattr(f, 'name', None):
            return None
        if getattr(f, 'size', 0) > HEADER_DOC_MAX_BYTES:
            raise forms.ValidationError('File must be 15 MB or smaller.')
        return f

    def clean_register_no(self):
        raw = (self.cleaned_data.get('register_no') or '').strip().upper()
        if not REGISTER_NO_RE.match(raw):
            raise forms.ValidationError(
                'Use format R- followed by digits (e.g. R-00001 or R-100000).'
            )
        return raw

    def clean_grn_category(self):
        cat = self.cleaned_data.get('grn_category')
        if cat and cat.pk not in GRN_CATEGORY_IDS:
            raise forms.ValidationError('GRN type must be RM or PM.')
        return cat

    def clean_grn_no(self):
        raw = (self.cleaned_data.get('grn_no') or '').strip().upper()
        if not raw:
            raise forms.ValidationError('GRN no. is required.')
        if not GRN_NO_RE.match(raw):
            raise forms.ValidationError(
                'Use format RM-… or PM-… (prefix plus digits, e.g. RM-00001 or PM-100000).'
            )
        cat = self.cleaned_data.get('grn_category')
        prefix = raw.split('-')[0]
        if cat and prefix != str(cat.pk).upper():
            raise forms.ValidationError('GRN no. prefix must match the selected GRN type.')

        inward_dt = self.cleaned_data.get('inward_dt')
        if inward_dt:
            # Enforce uniqueness within the same FY only (DB enforces too; this gives a nicer error).
            fy = validate_transaction_in_open_fy(inward_dt)
            qs = TrnInwHed.objects.filter(grn_no=raw, financial_year=fy)
            if self.instance and getattr(self.instance, 'pk', None):
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f'GRN no. "{raw}" already exists in financial year {fy.fy_display}.')
        return raw

    def clean_driver_no(self):
        val = self.cleaned_data.get('driver_no', '').strip()
        if not val:
            return None
        if not val.isdigit():
            raise forms.ValidationError('Driver contact must contain only digits.')
        if len(val) != 10:
            raise forms.ValidationError('Driver contact must be exactly 10 digits.')
        return val

    def clean(self):
        cd = super().clean()
        inv_dt = cd.get('inv_dt')
        inward_dt = cd.get('inward_dt')
        if inv_dt and inward_dt and inv_dt > inward_dt:
            self.add_error('inv_dt', 'Invoice date must not be after inward date.')
        if cd.get('driver_no') and not cd.get('driver_name'):
            self.add_error('driver_name', 'Driver name is required if driver contact is provided.')
        if inward_dt:
            # FY assignment happens in model.save(); the form just blocks closed/missing FYs.
            try:
                validate_transaction_in_open_fy(inward_dt)
            except ValidationError as e:
                raise forms.ValidationError(e.messages)
        return cd

    def clean_lines_json(self):
        raw = (self.cleaned_data.get('lines_json') or '').strip()
        grn_cat = self.cleaned_data.get('grn_category')
        if not raw or raw == '[]':
            raise forms.ValidationError('Add at least one item.')
        try:
            rows = json.loads(raw)
        except ValueError:
            raise forms.ValidationError('Invalid item data.')
        if not isinstance(rows, list):
            raise forms.ValidationError('Invalid item format.')

        cat_pk = grn_cat.pk if grn_cat else None
        if not cat_pk:
            raise forms.ValidationError('Select GRN type (RM or PM) before adding items.')

        seen_items = set()
        validated = []

        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f'Line {idx}: invalid row.')
            item_id = row.get('item_id')
            qty_raw = row.get('qty')
            batches_raw = row.get('batches') or []

            if not item_id:
                raise forms.ValidationError(f'Line {idx}: item is required.')
            try:
                item = MstItem.objects.select_related(
                    'item_category', 'uom', 'item_type',
                ).get(pk=int(item_id))
            except (MstItem.DoesNotExist, TypeError, ValueError):
                raise forms.ValidationError(f'Line {idx}: invalid item.')

            if item.item_category_id != cat_pk:
                raise forms.ValidationError(
                    f'Line {idx}: item "{item.item_name}" does not belong to the selected GRN category.'
                )

            if item.uom_id is None:
                raise forms.ValidationError(
                    f'Line {idx}: item "{item.item_name}" has no UOM. Set it on the Item master first.'
                )

            if item_id in seen_items:
                raise forms.ValidationError(f'Line {idx}: duplicate item — each item can appear only once.')
            seen_items.add(item_id)

            try:
                qty = Decimal(str(qty_raw))
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Line {idx}: quantity must be a number.')
            qty = qty.quantize(_QTY_QUANTIZE)
            if qty <= 0:
                raise forms.ValidationError(f'Line {idx}: quantity must be greater than zero.')

            maintain_batch = item.maintain_batch == 'Y'

            if not maintain_batch:
                if batches_raw:
                    raise forms.ValidationError(
                        f'Line {idx}: batches are not allowed for "{item.item_name}" '
                        '(Maintain Batches is No on the item).'
                    )
                validated.append({
                    'item': item,
                    'pkgsytle':pkgstyle,
                    'qty': qty,
                    'uom': item.uom,
                    'batches': [],
                })
                continue

            if not batches_raw:
                raise forms.ValidationError(
                    f'Line {idx}: batch lines are required for "{item.item_name}".'
                )
            if not isinstance(batches_raw, list):
                raise forms.ValidationError(f'Line {idx}: invalid batches.')

            batch_nos = set()
            batch_sum = Decimal('0')
            parsed_batches = []

            for bidx, b in enumerate(batches_raw, start=1):
                if not isinstance(b, dict):
                    raise forms.ValidationError(f'Line {idx} batch {bidx}: invalid data.')
                bn = (b.get('batch_no') or '').strip()
                if not bn:
                    raise forms.ValidationError(f'Line {idx} batch {bidx}: batch number is required.')
                if bn in batch_nos:
                    raise forms.ValidationError(
                        f'Line {idx}: duplicate batch number "{bn}" for this item.'
                    )
                batch_nos.add(bn)

                arn_no = (b.get('arn_no') or '').strip()
                if len(arn_no) > 20:
                    raise forms.ValidationError(
                        f'Line {idx} batch {bidx}: ARN no. must be at most 20 characters.'
                    )

                pack_style = (b.get('pack_style') or '').strip()
                if not pack_style:
                    raise forms.ValidationError(f'Line {idx} batch {bidx}: packing style is required.')
                if len(pack_style) > 30:
                    raise forms.ValidationError(
                        f'Line {idx} batch {bidx}: packing style must be 30 characters or fewer.'
                    )

                need_mfg = item.mfg_date == 'Y'
                need_exp = item.exp_date == 'Y'
                mfg_raw = b.get('mfg_dt')
                exp_raw = b.get('exp_dt')

                mfg_d = _parse_optional_date(mfg_raw, idx, bidx, 'manufacturing date')
                exp_d = _parse_optional_date(exp_raw, idx, bidx, 'expiry date')

                if need_mfg and mfg_d is None:
                    raise forms.ValidationError(
                        f'Line {idx} batch {bidx}: manufacturing date is required for this item.'
                    )
                if need_exp and exp_d is None:
                    raise forms.ValidationError(
                        f'Line {idx} batch {bidx}: expiry date is required for this item.'
                    )
                if exp_d is not None and mfg_d is None:
                    raise forms.ValidationError(
                        f'Line {idx} batch {bidx}: manufacturing date is required when expiry date is set.'
                    )
                if mfg_d is not None and exp_d is not None and exp_d <= mfg_d:
                    raise forms.ValidationError(
                        f'Line {idx} batch {bidx}: expiry date must be after manufacturing date.'
                    )

                try:
                    bqty = Decimal(str(b.get('batch_qty')))
                except (InvalidOperation, TypeError):
                    raise forms.ValidationError(f'Line {idx} batch {bidx}: batch quantity must be a number.')
                bqty = bqty.quantize(_QTY_QUANTIZE)
                if bqty <= 0:
                    raise forms.ValidationError(f'Line {idx} batch {bidx}: batch quantity must be > 0.')

                prod = None
                prod_raw = b.get('prod_id')
                if prod_raw not in (None, ''):
                    try:
                        prod = MstProd.objects.get(pk=int(prod_raw))
                    except (MstProd.DoesNotExist, TypeError, ValueError):
                        raise forms.ValidationError(f'Line {idx} batch {bidx}: invalid product.')

                batch_sum += bqty
                parsed_batches.append({
                    'batch_no': bn,
                    'arn_no': arn_no,
                    'pack_style': pack_style,
                    'mfg_dt': mfg_d,
                    'exp_dt': exp_d,
                    'batch_qty': bqty,
                    'product': prod,
                })

            batch_sum = batch_sum.quantize(_QTY_QUANTIZE)
            if batch_sum != qty:
                raise forms.ValidationError(
                    f'Line {idx}: sum of batch quantities ({batch_sum}) must equal line quantity ({qty}).'
                )

            validated.append({
                'item': item,
                'qty': qty,
                'pkgstyle': pkgstyle,
                'uom': item.uom,
                'batches': parsed_batches,
            })

        return validated

    def save(self):
        cd = self.cleaned_data
        lines = cd['lines_json']
        header_file = cd.get('header_document')
        prev_doc_path = self.instance.documents if self.instance else None
        try:
            with db_transaction.atomic():
                if self.instance:
                    # UPDATE path — patch the header, then replace all detail rows.
                    hed = self.instance
                    hed.inward_dt = cd['inward_dt']
                    hed.customer = cd['customer']
                    hed.register_no = cd['register_no']
                    hed.grn_category = cd['grn_category']
                    hed.grn_no = cd['grn_no']
                    hed.supplier = cd['supplier']
                    hed.inv_no = cd['inv_no']
                    hed.inv_dt = cd['inv_dt']
                    hed.transporter = cd['transporter']
                    hed.vehicle_no = (cd.get('vehicle_no') or '').strip()
                    hed.driver_name = cd.get('driver_name') or None
                    hed.driver_no = cd.get('driver_no') or None
                    hed.remarks = cd.get('remarks') or None
                    hed.save()
                    # Delete DTL2 first (references inward directly; no cascade from DTL1).
                    TrnInwDtl2.objects.filter(inward=hed).delete()
                    TrnInwDtl1.objects.filter(inward=hed).delete()
                else:
                    # CREATE path — build a fresh header.
                    hed = TrnInwHed(
                        inward_dt=cd['inward_dt'],
                        customer=cd['customer'],
                        register_no=cd['register_no'],
                        grn_category=cd['grn_category'],
                        grn_no=cd['grn_no'],
                        supplier=cd['supplier'],
                        inv_no=cd['inv_no'],
                        inv_dt=cd['inv_dt'],
                        transporter=cd['transporter'],
                        vehicle_no=(cd.get('vehicle_no') or '').strip(),
                        driver_name=cd.get('driver_name') or None,
                        driver_no=cd.get('driver_no') or None,
                        remarks=cd.get('remarks') or None,
                    )
                    hed.save()

                if header_file:
                    if prev_doc_path:
                        _delete_media_relative(prev_doc_path)
                    rel = _save_inward_header_file(
                        header_file,
                        cd['register_no'],
                        cd['supplier'],
                        cd['inward_dt'],
                    )
                    hed.documents = rel
                    hed.save(update_fields=['documents'])

                # (Re-)create detail rows for both create and update paths.
                for line in lines:
                    d1 = TrnInwDtl1(
                        inward=hed,
                        item=line['item'],
                        quantity=line['qty'],
                        pkg_style=line['pkgstyle'],
                        uom=line['uom'],
                    )
                    d1.save()
                    for b in line['batches']:
                        d2 = TrnInwDtl2(
                            inward=hed,
                            item=line['item'],
                            batch_no=b['batch_no'],
                            arn_no=b.get('arn_no') or '',
                            pack_style=b['pack_style'],
                            mfg_dt=b['mfg_dt'],
                            exp_dt=b['exp_dt'],
                            batch_qty=b['batch_qty'],
                            product=b['product'],
                        )
                        d2.save()
                return hed
        except IntegrityError:
            raise forms.ValidationError(
                'Could not save: duplicate register number or GRN number, or a database constraint failed.'
            ) from None


class SalesOrderForm(forms.Form):
    """Sales order — header + lines_json (Dtl1 + nested Dtl2)."""

    ord_rec_dt = forms.DateField(
        label='Order record date',
        error_messages={'required': 'Order record date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'soOrdRecDt'}),
    )
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select Customer —',
        error_messages={'required': 'Customer is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'soCustomer'}),
    )
    cust_ord_id = forms.CharField(
        max_length=20,
        label='Customer order ID',
        error_messages={'required': 'Customer order ID is required.'},
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'soCustOrdId', 'autocomplete': 'off'}),
    )
    cust_ord_date = forms.DateField(
        label='Customer order date',
        error_messages={'required': 'Customer order date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'soCustOrdDate'}),
    )
    delivery_add = forms.CharField(
        required=False,
        max_length=200,
        label='Delivery address',
        widget=forms.Textarea(attrs={'class': 'cu-textarea', 'id': 'soDeliveryAdd', 'rows': 3}),
    )
    pkg_fwd_amt = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0'),
        label='Packing / forwarding',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'soPkgFwd', 'step': '0.01', 'min': '0'}),
    )
    frieght_amt = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0'),
        label='Freight',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'soFreight', 'step': '0.01', 'min': '0'}),
    )
    oth_charges = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0'),
        label='Other charges',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'soOthCharges', 'step': '0.01', 'min': '0'}),
    )
    round_off = forms.DecimalField(
        required=False,
        max_digits=6,
        decimal_places=2,
        initial=Decimal('0'),
        label='Round off',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'soRoundOff', 'step': '0.01', 'min': '-1', 'max': '1'}),
    )
    terms_cond = forms.CharField(
        required=False,
        max_length=1000,
        label='Terms and conditions',
        widget=forms.Textarea(attrs={'class': 'cu-textarea', 'id': 'soTerms', 'rows': 3}),
    )
    remarks = forms.CharField(
        required=False,
        max_length=500,
        label='Remarks',
        widget=forms.Textarea(attrs={'class': 'cu-textarea', 'id': 'soRemarks', 'rows': 3}),
    )
    header_document = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(list(HEADER_DOC_EXTENSIONS))],
        widget=forms.FileInput(attrs={
            'class': 'inw-header-doc-input',
            'id': 'soHeaderDocInput',
            'accept': '.pdf,image/*',
        }),
        label='Document',
    )
    lines_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'soLinesJson'}),
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')

    def get_initial(self):
        if not self.instance:
            return {'ord_rec_dt': timezone.localdate()}
        h = self.instance
        disp_map = defaultdict(list)
        for d2 in h.dispatch_lines.all():
            disp_map[d2.product_id].append({
                'disp_sche_dt': str(d2.disp_sche_dt),
                'disp_qty': str(d2.disp_qty),
                'remarks': d2.remarks or '',
            })
        lines = []
        for d1 in h.lines.all():
            lines.append({
                'prod_id': d1.product_id,
                'pkg_style_id': d1.packing_style_id,
                'order_qty': str(d1.order_qty),
                'rate': str(d1.rate),
                'gst_type': d1.gst_type,
                'gst_per': str(d1.gst_per),
                'export_type': d1.export_type,
                'dispatches': disp_map.get(d1.product_id, []),
            })
        return {
            'ord_rec_dt': h.ord_rec_dt,
            'customer': h.customer_id,
            'cust_ord_id': h.cust_ord_id,
            'cust_ord_date': h.cust_ord_date,
            'delivery_add': h.delivery_add or '',
            'pkg_fwd_amt': h.pkg_fwd_amt,
            'frieght_amt': h.frieght_amt,
            'oth_charges': h.oth_charges,
            'round_off': h.round_off,
            'terms_cond': h.terms_cond or '',
            'remarks': h.remarks or '',
            'lines_json': json.dumps(lines),
        }

    def clean_header_document(self):
        f = self.cleaned_data.get('header_document')
        if not f or not getattr(f, 'name', None):
            return None
        if getattr(f, 'size', 0) > HEADER_DOC_MAX_BYTES:
            raise forms.ValidationError('File must be 15 MB or smaller.')
        return f

    def clean_cust_ord_id(self):
        raw = (self.cleaned_data.get('cust_ord_id') or '').strip()
        if not raw:
            raise forms.ValidationError('Customer order ID is required.')
        cust = self.cleaned_data.get('customer')
        if cust:
            qs = TrnSlsOrdHed.objects.filter(customer=cust, cust_ord_id=raw)
            if self.instance and getattr(self.instance, 'pk', None):
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'Customer order ID "{raw}" already exists for this customer.'
                )
        return raw

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

    def clean_frieght_amt(self):
        return self._nonneg_money('frieght_amt', 'Freight')

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
        ord_rec_dt = self.cleaned_data.get('ord_rec_dt')
        if not ord_rec_dt:
            raise forms.ValidationError('Enter order record date before adding product lines.')
        if not raw or raw == '[]':
            raise forms.ValidationError('Add at least one product line.')
        try:
            rows = json.loads(raw)
        except ValueError:
            raise forms.ValidationError('Invalid line data.')
        if not isinstance(rows, list):
            raise forms.ValidationError('Invalid line format.')

        seen_triplets = set()
        validated = []

        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f'Line {idx}: invalid row.')

            prod_id = row.get('prod_id')
            pkg_id = row.get('pkg_style_id')
            oq_raw = row.get('order_qty')
            rate_raw = row.get('rate')
            gst_type = (row.get('gst_type') or '').strip()
            gst_per_raw = row.get('gst_per')
            export_type = (row.get('export_type') or '').strip()
            dispatches_raw = row.get('dispatches') or []

            if not prod_id:
                raise forms.ValidationError(f'Line {idx}: product is required.')
            try:
                product = MstProd.objects.select_related('prod_type').get(pk=int(prod_id))
            except (MstProd.DoesNotExist, TypeError, ValueError):
                raise forms.ValidationError(f'Line {idx}: invalid product.')

            hsn = (product.hsn_code or '').strip()
            if not hsn:
                raise forms.ValidationError(
                    f'Line {idx}: product "{product.prod_name}" has no HSN code on the master.'
                )

            if not pkg_id:
                raise forms.ValidationError(f'Line {idx}: packing style is required.')
            try:
                packing = MstPkgStyle.objects.get(pk=int(pkg_id))
            except (MstPkgStyle.DoesNotExist, TypeError, ValueError):
                raise forms.ValidationError(f'Line {idx}: invalid packing style.')

            if packing.pkg_type_id != product.prod_type_id:
                raise forms.ValidationError(
                    f'Line {idx}: packing style must match the product type of the selected product.'
                )

            # Uniqueness in a single order: (product + packing style + rate)
            # Note: rate is validated below; we will add to seen_triplets after rate parsing.

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
                order_qty = Decimal(str(oq_raw))
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Line {idx}: order quantity must be a number.')
            order_qty = order_qty.quantize(_SO_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
            if order_qty <= 0:
                raise forms.ValidationError(f'Line {idx}: order quantity must be greater than zero.')

            try:
                rate = Decimal(str(rate_raw))
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Line {idx}: rate must be a number.')
            rate = rate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if rate <= 0:
                raise forms.ValidationError(f'Line {idx}: rate must be greater than zero.')

            trip_key = (str(product.pk), str(packing.pk), str(rate))
            if trip_key in seen_triplets:
                raise forms.ValidationError(
                    f'Line {idx}: duplicate product entry (same product, packing style, and rate).'
                )
            seen_triplets.add(trip_key)

            if not export_type:
                raise forms.ValidationError(f'Line {idx}: export type is required.')
            if len(export_type) > 100:
                raise forms.ValidationError(f'Line {idx}: export type must be 100 characters or fewer.')

            pkg_val = int(packing.pkg_style_value)
            if pkg_val <= 0:
                raise forms.ValidationError(f'Line {idx}: packing value must be greater than zero.')

            # order_qty is entered in Lakhs.
            ord_qty_nos = (order_qty * Decimal('100000')).quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)
            taxable = ((ord_qty_nos / Decimal(pkg_val)) * rate).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)

            cgst, sgst, igst = _line_gst_amounts(taxable, gst_per, gst_type)
            prod_amt = (taxable + cgst + sgst + igst).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)

            if not isinstance(dispatches_raw, list) or not dispatches_raw:
                raise forms.ValidationError(f'Line {idx}: add at least one dispatch row.')

            disp_sum = Decimal('0')
            disp_parsed = []
            seen_dt = set()
            for j, d in enumerate(dispatches_raw, start=1):
                if not isinstance(d, dict):
                    raise forms.ValidationError(f'Line {idx} dispatch {j}: invalid data.')
                ds_raw = d.get('disp_sche_dt')
                dq_raw = d.get('disp_qty')
                rem = (d.get('remarks') or '').strip() or None
                if rem and len(rem) > 20:
                    raise forms.ValidationError(f'Line {idx} dispatch {j}: remarks must be 20 characters or fewer.')
                d_dt = ds_raw if hasattr(ds_raw, 'year') else parse_date(str(ds_raw or '').strip())
                if not d_dt:
                    raise forms.ValidationError(f'Line {idx} dispatch {j}: invalid schedule date.')
                if ord_rec_dt and d_dt < ord_rec_dt:
                    raise forms.ValidationError(
                        f'Line {idx} dispatch {j}: schedule date must not be before order record date.'
                    )
                key = str(d_dt)
                if key in seen_dt:
                    raise forms.ValidationError(
                        f'Line {idx}: duplicate dispatch schedule date for the same product.'
                    )
                seen_dt.add(key)
                try:
                    dq = Decimal(str(dq_raw))
                except (InvalidOperation, TypeError):
                    raise forms.ValidationError(f'Line {idx} dispatch {j}: dispatch qty must be a number.')
                dq = dq.quantize(_SO_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
                if dq <= 0:
                    raise forms.ValidationError(f'Line {idx} dispatch {j}: dispatch qty must be greater than zero.')
                disp_sum += dq
                disp_parsed.append({'disp_sche_dt': d_dt, 'disp_qty': dq, 'remarks': rem})

            disp_sum = disp_sum.quantize(_SO_QTY_QUANTIZE, rounding=ROUND_HALF_UP)
            if disp_sum != order_qty:
                raise forms.ValidationError(
                    f'Line {idx}: sum of dispatch quantities ({disp_sum}) must equal order quantity ({order_qty}).'
                )

            validated.append({
                'product': product,
                'packing_style': packing,
                'hsn_no': hsn,
                'order_qty': order_qty,
                'ord_qty_nos': ord_qty_nos,
                'rate': rate,
                'taxable_amt': taxable,
                'gst_type': gst_type,
                'gst_per': gst_per,
                'cgst_amt': cgst,
                'sgst_amt': sgst,
                'igst_amt': igst,
                'prod_amt': prod_amt,
                'export_type': export_type,
                'dispatches': disp_parsed,
            })

        return validated

    def clean(self):
        cd = super().clean()
        ord_rec_dt = cd.get('ord_rec_dt')
        cust_ord_date = cd.get('cust_ord_date')
        if ord_rec_dt and cust_ord_date and cust_ord_date > ord_rec_dt:
            self.add_error('cust_ord_date', 'Customer order date must not be after order record date.')
        if ord_rec_dt:
            try:
                fy = validate_transaction_in_open_fy(ord_rec_dt)
            except ValidationError as e:
                raise forms.ValidationError(e.messages)
            if ord_rec_dt < fy.start_date or ord_rec_dt > fy.end_date:
                self.add_error('ord_rec_dt', 'Order record date must fall within the financial year.')
            if cust_ord_date:
                if cust_ord_date < fy.start_date or cust_ord_date > fy.end_date:
                    self.add_error(
                        'cust_ord_date',
                        'Customer order date must fall within the financial year of the order record date.',
                    )
        return cd

    def save(self):
        cd = self.cleaned_data
        lines = cd['lines_json']
        header_file = cd.get('header_document')
        prev_doc = self.instance.document_path if self.instance else None

        taxable_sum = sum((ln['taxable_amt'] for ln in lines), Decimal('0'))
        cgst_sum = sum((ln['cgst_amt'] for ln in lines), Decimal('0'))
        sgst_sum = sum((ln['sgst_amt'] for ln in lines), Decimal('0'))
        igst_sum = sum((ln['igst_amt'] for ln in lines), Decimal('0'))

        pkg = cd['pkg_fwd_amt']
        frt = cd['frieght_amt']
        oth = cd['oth_charges']
        rnd = cd['round_off']
        total = (
            taxable_sum + pkg + frt + oth + cgst_sum + sgst_sum + igst_sum + rnd
        ).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)

        try:
            with db_transaction.atomic():
                prev_line_map = {}
                if self.instance:
                    # Snapshot allocation status before deleting old lines.
                    for old in TrnSlsOrdDtl1.objects.filter(order=self.instance).only(
                        'product_id', 'packing_style_id', 'rate', 'remaining_qty', 'is_completed',
                    ):
                        prev_line_map[(old.product_id, old.packing_style_id, str(old.rate))] = {
                            'remaining_qty': old.remaining_qty,
                            'is_completed': old.is_completed,
                        }

                if self.instance:
                    hed = self.instance
                    hed.ord_rec_dt = cd['ord_rec_dt']
                    hed.customer = cd['customer']
                    hed.cust_ord_id = cd['cust_ord_id']
                    hed.cust_ord_date = cd['cust_ord_date']
                    hed.delivery_add = cd.get('delivery_add') or None
                    hed.pkg_fwd_amt = pkg
                    hed.frieght_amt = frt
                    hed.oth_charges = oth
                    hed.round_off = rnd
                    hed.taxable_val = taxable_sum
                    hed.cgst_amt = cgst_sum
                    hed.sgst_amt = sgst_sum
                    hed.igst_amt = igst_sum
                    hed.total_amt = total
                    hed.terms_cond = cd.get('terms_cond') or None
                    hed.remarks = cd.get('remarks') or None
                    hed.save()
                    TrnSlsOrdDtl2.objects.filter(order=hed).delete()
                    TrnSlsOrdDtl1.objects.filter(order=hed).delete()
                else:
                    hed = TrnSlsOrdHed(
                        ord_rec_dt=cd['ord_rec_dt'],
                        customer=cd['customer'],
                        cust_ord_id=cd['cust_ord_id'],
                        cust_ord_date=cd['cust_ord_date'],
                        delivery_add=cd.get('delivery_add') or None,
                        pkg_fwd_amt=pkg,
                        frieght_amt=frt,
                        oth_charges=oth,
                        round_off=rnd,
                        taxable_val=taxable_sum,
                        cgst_amt=cgst_sum,
                        sgst_amt=sgst_sum,
                        igst_amt=igst_sum,
                        total_amt=total,
                        terms_cond=cd.get('terms_cond') or None,
                        remarks=cd.get('remarks') or None,
                    )
                    hed.save()

                if header_file:
                    if prev_doc:
                        _delete_media_relative(prev_doc)
                    rel = _save_sales_order_header_file(header_file, cd['customer'], cd['ord_rec_dt'])
                    hed.document_path = rel
                    hed.save(update_fields=['document_path'])

                for ln in lines:
                    d1 = TrnSlsOrdDtl1(
                        order=hed,
                        product=ln['product'],
                        hsn_no=ln['hsn_no'],
                        packing_style=ln['packing_style'],
                        order_qty=ln['order_qty'],
                        remaining_qty=ln['order_qty'],
                        is_completed=False,
                        ord_qty_nos=ln['ord_qty_nos'],
                        rate=ln['rate'],
                        taxable_amt=ln['taxable_amt'],
                        gst_type=ln['gst_type'],
                        gst_per=ln['gst_per'],
                        cgst_amt=ln['cgst_amt'],
                        sgst_amt=ln['sgst_amt'],
                        igst_amt=ln['igst_amt'],
                        prod_amt=ln['prod_amt'],
                        export_type=ln['export_type'],
                    )
                    if self.instance:
                        key = (ln['product'].pk, ln['packing_style'].pk, str(ln['rate']))
                        prev = prev_line_map.get(key)
                        if prev:
                            # Clamp remaining to the new ordered qty.
                            rem = prev['remaining_qty']
                            if rem is not None and rem > d1.order_qty:
                                rem = d1.order_qty
                            d1.remaining_qty = rem if rem is not None else d1.order_qty
                            d1.is_completed = bool(prev['is_completed']) or (d1.remaining_qty == 0)
                    d1.save()
                    for dp in ln['dispatches']:
                        TrnSlsOrdDtl2(
                            order=hed,
                            product=ln['product'],
                            disp_sche_dt=dp['disp_sche_dt'],
                            disp_qty=dp['disp_qty'],
                            remarks=dp['remarks'],
                        ).save()
                return hed
        except IntegrityError:
            raise forms.ValidationError(
                'Could not save: duplicate customer order ID or a database constraint failed.'
            ) from None


def _batch_ladder_quantities(target, size, count, quant):
    """Split ``target`` into ``count`` parts: first (count-1) equal ``size``, last is remainder."""
    target = Decimal(str(target)).quantize(quant)
    size = Decimal(str(size)).quantize(quant)
    if count < 1:
        raise forms.ValidationError('Invalid batch range.')
    if target == 0:
        if size != 0:
            raise forms.ValidationError('When order quantity (nos.) is zero, batch size (nos.) must be zero.')
        return [Decimal('0').quantize(quant)] * count
    if size <= 0:
        raise forms.ValidationError('Batch size must be greater than zero.')
    last = (target - size * (count - 1)).quantize(quant)
    if last <= 0 or last > size:
        raise forms.ValidationError(
            'Total quantity does not fit the batch count and batch size '
            '(each batch except the last must equal batch size; the last must be positive and not exceed batch size).'
        )
    rows = [size] * (count - 1) + [last]
    if sum(rows, Decimal('0')).quantize(quant) != target:
        raise forms.ValidationError('Total batch quantity mismatch.')
    return rows


class BatchAllocationForm(forms.Form):
    """Create TrnBatchHed + TrnBatchDtl from sales order line (document-driven)."""

    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select Customer —',
        error_messages={'required': 'Customer is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'baCustomer'}),
    )
    order_id = forms.IntegerField(
        label='Order',
        error_messages={'required': 'Order is required.', 'invalid': 'Invalid order selection.'},
        widget=forms.HiddenInput(attrs={'id': 'baOrderId'}),
    )
    order_line_id = forms.IntegerField(
        label='Order line',
        error_messages={'required': 'Product is required.', 'invalid': 'Invalid product.'},
        widget=forms.HiddenInput(attrs={'id': 'baOrderLineId'}),
    )
    partial = forms.BooleanField(
        required=False,
        initial=False,
        label='Partial allocation',
        widget=forms.CheckboxInput(attrs={'id': 'baPartialYn', 'class': 'ba-checkbox'}),
    )
    partial_qty_l = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Partial qty (Lacs)',
        widget=forms.NumberInput(attrs={'class': 'cu-input ba-input-narrow', 'id': 'baPartialL', 'step': '0.01'}),
    )
    partial_qty_n = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=0,
        label='Partial qty (Nos.)',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input ba-input-narrow',
            'id': 'baPartialN',
            'step': '1',
            'readonly': 'readonly',
            'tabindex': '-1',
        }),
    )
    batch_size_l = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        label='Batch size (Lacs)',
        widget=forms.NumberInput(attrs={'class': 'cu-input ba-input-narrow', 'id': 'baBatchSizeL', 'step': '0.01'}),
    )
    batch_size_n = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=0,
        label='Batch size (Nos.)',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input ba-input-narrow',
            'id': 'baBatchSizeN',
            'step': '1',
            'readonly': 'readonly',
            'tabindex': '-1',
        }),
    )
    batch_from = forms.IntegerField(
        min_value=1,
        label='Batch no. from',
        widget=forms.NumberInput(attrs={'class': 'cu-input ba-seq-input', 'id': 'baBatchFrom', 'min': '1'}),
    )
    batch_to = forms.IntegerField(
        min_value=1,
        label='Batch no. to',
        widget=forms.NumberInput(attrs={'class': 'cu-input ba-seq-input', 'id': 'baBatchTo', 'min': '1'}),
    )
    mfg_dt = forms.CharField(
        max_length=8,
        label='MFG date',
        widget=forms.TextInput(attrs={
            'class': 'cu-input ba-mmm-input',
            'id': 'baMfgDt',
            'type': 'month',
            'placeholder': 'YYYY-MM',
            'autocomplete': 'off',
        }),
    )
    exp_dt = forms.CharField(
        max_length=8,
        label='EXP date',
        widget=forms.TextInput(attrs={
            'class': 'cu-input ba-mmm-input',
            'id': 'baExpDt',
            'type': 'month',
            'placeholder': 'YYYY-MM',
            'autocomplete': 'off',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')

    def clean_mfg_dt(self):
        raw = self.cleaned_data.get('mfg_dt')
        y, m, norm = _parse_month_any(raw, 'Manufacturing date')
        # Allow future months for planned batch creation; still validated against EXP in clean().
        return norm

    def clean_exp_dt(self):
        raw = self.cleaned_data.get('exp_dt')
        _y, _m, norm = _parse_month_any(raw, 'Expiry date')
        return norm

    def clean(self):
        cd = super().clean()
        cust = cd.get('customer')
        oid = cd.get('order_id')
        line_id = cd.get('order_line_id')
        if not cust or oid is None or line_id is None:
            return cd

        try:
            order = TrnSlsOrdHed.objects.select_related('customer').get(pk=int(oid))
        except (TrnSlsOrdHed.DoesNotExist, TypeError, ValueError):
            self.add_error('order_id', 'Invalid order selection.')
            return cd

        if order.customer_id != cust.pk:
            self.add_error('order_id', 'Invalid order selection.')
            return cd

        try:
            line = TrnSlsOrdDtl1.objects.select_related('order', 'product').get(
                pk=int(line_id),
            )
        except (TrnSlsOrdDtl1.DoesNotExist, TypeError, ValueError):
            self.add_error('order_line_id', 'Product must belong to selected order.')
            return cd

        if line.order_id != order.pk:
            self.add_error('order_line_id', 'Product must belong to selected order.')
            return cd

        product = line.product

        if line.is_completed or line.remaining_qty <= 0:
            self.add_error('order_line_id', 'This line is already completed.')
            return cd

        order_qty_l = line.remaining_qty.quantize(_BATCH_L_QUANTIZE)
        order_qty_n = (order_qty_l * Decimal('100000')).quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)
        if order_qty_l <= 0:
            self.add_error('order_line_id', 'Remaining quantity (Lacs) must be greater than zero.')
            return cd

        try:
            cust_prod = MstCustProd.objects.get(customer=cust, product=product)
        except MstCustProd.DoesNotExist:
            self.add_error(
                'order_line_id',
                'Link this product to the customer on the Customer master and set a 3-character batch abbreviation.',
            )
            return cd

        abbr = (cust_prod.batch_abbr or '').strip().upper()
        if len(abbr) != 3:
            self.add_error(
                'order_line_id',
                'Batch abbreviation on customer product master must be exactly 3 characters.',
            )
            return cd

        partial_on = bool(cd.get('partial'))
        partial_yn = 'Y' if partial_on else 'N'

        if partial_on:
            pl = cd.get('partial_qty_l')
            if pl is None:
                self.add_error('partial_qty_l', 'Partial quantity (Lacs) is required when partial allocation is enabled.')
            if self.errors:
                return cd
            pl = Decimal(str(pl)).quantize(_BATCH_L_QUANTIZE)
            pn = (pl * Decimal('100000')).quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)
            if pl <= 0:
                self.add_error('partial_qty_l', 'Partial quantity must be greater than zero.')
            if order_qty_n > 0 and pn <= 0:
                self.add_error('partial_qty_n', 'Partial quantity (nos.) must be greater than zero.')
            if order_qty_n == 0 and pn != 0:
                self.add_error('partial_qty_n', 'Partial quantity (nos.) must be zero for this order line.')
            if pn < 0:
                self.add_error('partial_qty_n', 'Partial quantity (nos.) must be zero or greater.')
            if pl > order_qty_l:
                self.add_error('partial_qty_l', 'Partial quantity exceeds order quantity.')
            if pn > order_qty_n:
                self.add_error('partial_qty_n', 'Partial quantity exceeds order quantity.')
            target_l, target_n = pl, pn
        else:
            pl = pn = None
            if cd.get('partial_qty_l') not in (None, '') or cd.get('partial_qty_n') not in (None, ''):
                # tolerate stray POST values when unchecked
                pass
            target_l, target_n = order_qty_l, order_qty_n

        if self.errors:
            return cd

        bf = cd.get('batch_from')
        bt = cd.get('batch_to')
        if bf is None or bt is None:
            return cd
        if bf > bt:
            self.add_error('batch_to', 'Invalid batch range.')
            return cd
        count = bt - bf + 1
        if count < 1:
            self.add_error('batch_to', 'Invalid batch range.')
            return cd

        overlap = TrnBatchHed.objects.filter(order_line=line).filter(
            batch_from__lte=bt,
            batch_to__gte=bf,
        ).exists()
        if overlap:
            self.add_error('batch_from', 'Batch range overlaps with existing batches for this order and product.')

        bsl = cd.get('batch_size_l')
        if bsl is None:
            return cd
        bsl = Decimal(str(bsl)).quantize(_BATCH_L_QUANTIZE)
        bsn = (bsl * Decimal('100000')).quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)

        if bsl <= 0:
            self.add_error('batch_size_l', 'Batch size must be greater than zero.')
        if target_n > 0 and bsn <= 0:
            self.add_error('batch_size_n', 'Batch size (nos.) must be greater than zero.')
        if target_n == 0 and bsn != 0:
            self.add_error('batch_size_n', 'Batch size (nos.) must be zero when order quantity (nos.) is zero.')
        if bsl > target_l:
            self.add_error('batch_size_l', 'Batch size must not exceed allowed quantity.')
        if target_n > 0 and bsn > target_n:
            self.add_error('batch_size_n', 'Batch size must not exceed allowed quantity.')

        mfg = cd.get('mfg_dt')
        exp = cd.get('exp_dt')
        if mfg and exp and not self.errors:
            y1, m1, _ = _parse_mmm_yyyy(mfg, 'Manufacturing date')
            y2, m2, _ = _parse_mmm_yyyy(exp, 'Expiry date')
            if _ym_key(y2, m2) <= _ym_key(y1, m1):
                self.add_error('exp_dt', 'Expiry date must be greater than manufacturing date.')

        if self.errors:
            return cd

        try:
            qtys_l = _batch_ladder_quantities(target_l, bsl, count, _BATCH_L_QUANTIZE)
            qtys_n = _batch_ladder_quantities(target_n, bsn, count, _BATCH_N_QUANTIZE)
        except forms.ValidationError as e:
            self.add_error('batch_size_l', e)
            return cd

        seqs = list(range(bf, bt + 1))
        lines = []
        batch_nos = []
        for seq, ql, qn in zip(seqs, qtys_l, qtys_n):
            bn = f'{abbr}{seq}'
            if len(bn) > 15:
                self.add_error('batch_to', 'Generated batch number would exceed 15 characters.')
                return cd
            batch_nos.append(bn)
            lines.append({
                'batch_no': bn,
                'batch_qty_l': ql,
                'batch_qty_n': qn,
            })

        dup_exists = TrnBatchDtl.objects.filter(batch_no__in=batch_nos).exists()
        if dup_exists:
            self.add_error('batch_from', 'Batch already exists.')

        if self.errors:
            return cd

        cd['_save_context'] = {
            'customer': cust,
            'order': order,
            'order_line': line,
            'product': product,
            'partial_yn': partial_yn,
            'partial_qty_l': pl,
            'partial_qty_n': pn,
            'batch_abbr': abbr,
            'batch_size_l': bsl,
            'batch_size_n': bsn,
            'batch_from': bf,
            'batch_to': bt,
            'mfg_dt': mfg,
            'exp_dt': exp,
            'lines': lines,
        }
        return cd

    def save(self):
        ctx = self.cleaned_data['_save_context']
        lines = ctx['lines']
        try:
            with db_transaction.atomic():
                # Concurrency safety: lock the sales order line and re-check remaining before saving.
                locked_line = (
                    TrnSlsOrdDtl1.objects.select_for_update()
                    .select_related('order', 'product')
                    .get(pk=ctx['order_line'].pk)
                )
                if locked_line.is_completed or locked_line.remaining_qty <= 0:
                    raise forms.ValidationError({'order_line_id': 'This line is already completed.'})

                alloc_l = ctx['partial_qty_l'] if ctx['partial_yn'] == 'Y' else locked_line.remaining_qty
                alloc_l = Decimal(str(alloc_l)).quantize(_BATCH_L_QUANTIZE)
                if alloc_l <= 0:
                    raise forms.ValidationError({'partial_qty_l': 'Allocation quantity must be greater than zero.'})
                if alloc_l > locked_line.remaining_qty:
                    raise forms.ValidationError({'partial_qty_l': 'Allocation exceeds remaining quantity.'})

                hed = TrnBatchHed(
                    customer=ctx['customer'],
                    order=ctx['order'],
                    order_line=locked_line,
                    product=ctx['product'],
                    batch_size_l=ctx['batch_size_l'],
                    batch_size_n=ctx['batch_size_n'],
                    partial_yn=ctx['partial_yn'],
                    partial_qty_l=ctx['partial_qty_l'],
                    partial_qty_n=ctx['partial_qty_n'],
                    batch_abbr=ctx['batch_abbr'],
                    batch_from=ctx['batch_from'],
                    batch_to=ctx['batch_to'],
                )
                hed.save()
                for row in lines:
                    TrnBatchDtl(
                        batch=hed,
                        batch_no=row['batch_no'],
                        batch_qty_l=row['batch_qty_l'],
                        batch_qty_n=row['batch_qty_n'],
                        mfg_dt=ctx['mfg_dt'],
                        exp_dt=ctx['exp_dt'],
                        log_sheet_flg='N',
                    ).save()

                # Update remaining qty.
                new_rem = (locked_line.remaining_qty - alloc_l).quantize(_BATCH_L_QUANTIZE, rounding=ROUND_HALF_UP)
                if new_rem < 0:
                    new_rem = Decimal('0').quantize(_BATCH_L_QUANTIZE)
                locked_line.remaining_qty = new_rem
                locked_line.is_completed = (new_rem == 0)
                locked_line.save(update_fields=['remaining_qty', 'is_completed'])
                return hed
        except IntegrityError:
            raise forms.ValidationError(
                'Batch already exists or a database constraint failed.'
            ) from None


class LogSheetForm(forms.Form):
    """Create one granulation log sheet row; set batch log_sheet_flg when fully logged."""

    gran_dt = forms.DateField(
        label='Granulation date',
        error_messages={'required': 'Granulation date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'lsGranDt'}),
    )
    section = forms.ModelChoiceField(
        queryset=MstSection.objects.none(),
        label='Section',
        empty_label='— Select section —',
        error_messages={'required': 'Section is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'lsSection'}),
    )
    shift = forms.ChoiceField(
        choices=LOGSHEET_SHIFT_CHOICES,
        label='Shift',
        error_messages={'required': 'Shift is required.'},
        widget=forms.Select(attrs={'class': 'cu-select', 'id': 'lsShift'}),
    )
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select customer —',
        error_messages={'required': 'Customer is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'lsCustomer'}),
    )
    product = forms.ModelChoiceField(
        queryset=MstProd.objects.none(),
        label='Product',
        empty_label='— Select product —',
        error_messages={'required': 'Product is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'lsProduct'}),
    )
    batch_dtl_id = forms.IntegerField(
        label='Batch',
        error_messages={'required': 'Select a pending batch.', 'invalid': 'Invalid batch selection.'},
        widget=forms.HiddenInput(attrs={'id': 'lsBatchDtlId'}),
    )
    layer_slot = forms.ChoiceField(
        label='Layer / colour',
        choices=LOGSHEET_LAYER_SLOT_CHOICES,
        initial=LOGSHEET_LAYER_SLOT_SINGLE,
        widget=forms.HiddenInput(attrs={'id': 'lsLayerSlot'}),
    )
    blend_dt = forms.DateField(
        required=False,
        label='Blending date',
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'lsBlendDt'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')
        self.fields['product'].queryset = MstProd.objects.all().order_by('prod_name')
        gran_ids = [
            s.section_id
            for s in MstSection.objects.all().only('section_id', 'section_name').order_by('section_name')
            if _granulation_section_key(s.section_name)
        ]
        self.fields['section'].queryset = MstSection.objects.filter(section_id__in=gran_ids).order_by(
            'section_name',
        )

    def clean_section(self):
        sec = self.cleaned_data.get('section')
        if sec and not _granulation_section_key(sec.section_name):
            raise forms.ValidationError('Section must be Granulation-I or Granulation-II.')
        return sec

    def clean_gran_dt(self):
        d = self.cleaned_data.get('gran_dt')
        if d:
            try:
                validate_transaction_in_open_fy(d)
            except ValidationError as e:
                raise forms.ValidationError(list(e.messages))
            if d > timezone.localdate():
                raise forms.ValidationError('Granulation date cannot be in the future.')
        return d

    def clean(self):
        cd = super().clean()
        cust = cd.get('customer')
        prod = cd.get('product')
        bpk = cd.get('batch_dtl_id')
        if not cust or not prod or bpk is None:
            return cd

        if not MstCustProd.objects.filter(customer=cust, product=prod).exists():
            self.add_error('product', 'This product is not linked to the selected customer.')

        try:
            line = (
                TrnBatchDtl.objects.select_related('batch', 'batch__customer', 'batch__product', 'batch__order')
                .get(pk=int(bpk))
            )
        except (TrnBatchDtl.DoesNotExist, TypeError, ValueError):
            self.add_error('batch_dtl_id', 'Invalid batch allocation line.')
            return cd

        if line.batch.customer_id != cust.pk:
            self.add_error('batch_dtl_id', 'Batch does not belong to the selected customer.')
        if line.batch.product_id != prod.pk:
            self.add_error('batch_dtl_id', 'Batch does not belong to the selected product.')

        if line.log_sheet_flg == 'Y':
            self.add_error('batch_dtl_id', 'This batch is already fully logged.')

        line_prod = line.batch.product
        pl = line_prod.tablet_layer
        slot = (cd.get('layer_slot') or LOGSHEET_LAYER_SLOT_SINGLE).strip()
        if pl == MstProd.LAYER_SINGLE:
            if slot != LOGSHEET_LAYER_SLOT_SINGLE:
                self.add_error('layer_slot', 'Single-layer batches use one log sheet only.')
            elif TrnLogSheet.objects.filter(batch_line=line, layer_slot=LOGSHEET_LAYER_SLOT_SINGLE).exists():
                self.add_error('batch_dtl_id', 'This batch is already used on a log sheet.')
        elif pl == MstProd.LAYER_DOUBLE:
            if slot not in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
                self.add_error('layer_slot', 'Choose first or second colour for this double-layer batch.')
            elif TrnLogSheet.objects.filter(batch_line=line, layer_slot=slot).exists():
                self.add_error('batch_dtl_id', 'This colour is already logged for this batch.')
        else:
            self.add_error('batch_dtl_id', 'Unsupported tablet layer on product.')

        mfg = (line.mfg_dt or '').strip()
        exp = (line.exp_dt or '').strip()
        if mfg and exp:
            try:
                y1, m1, _ = _parse_mmm_yyyy(mfg, 'Manufacturing')
                y2, m2, _ = _parse_mmm_yyyy(exp, 'Expiry')
            except forms.ValidationError as e:
                self.add_error('batch_dtl_id', e)
                return cd
            if _ym_key(y2, m2) <= _ym_key(y1, m1):
                self.add_error('batch_dtl_id', 'Batch expiry must be after manufacturing month.')

        cd['_batch_line'] = line
        return cd

    def save(self):
        cd = self.cleaned_data
        line = cd['_batch_line']
        slot = cd['layer_slot']
        try:
            with db_transaction.atomic():
                locked = (
                    TrnBatchDtl.objects.select_for_update()
                    .select_related('batch__product')
                    .get(pk=line.pk)
                )
                if locked.log_sheet_flg != 'N':
                    raise forms.ValidationError({'batch_dtl_id': 'This batch was just completed by another user.'})
                pl = locked.batch.product.tablet_layer
                if pl == MstProd.LAYER_SINGLE:
                    if TrnLogSheet.objects.filter(batch_line_id=locked.pk, layer_slot=LOGSHEET_LAYER_SLOT_SINGLE).exists():
                        raise forms.ValidationError({'batch_dtl_id': 'This batch is already used on a log sheet.'})
                elif TrnLogSheet.objects.filter(batch_line_id=locked.pk, layer_slot=slot).exists():
                    raise forms.ValidationError({'batch_dtl_id': 'This colour is already logged for this batch.'})

                row = TrnLogSheet(
                    section=cd['section'],
                    gran_dt=cd['gran_dt'],
                    customer=cd['customer'],
                    shift_id=cd['shift'],
                    product=cd['product'],
                    batch_line=locked,
                    blend_dt=cd.get('blend_dt'),
                    dpr_flg='N',
                    layer_slot=slot,
                )
                row.save()
                if pl == MstProd.LAYER_SINGLE:
                    locked.log_sheet_flg = 'Y'
                else:
                    has_first = TrnLogSheet.objects.filter(
                        batch_line_id=locked.pk,
                        layer_slot=LOGSHEET_LAYER_SLOT_FIRST,
                    ).exists()
                    has_second = TrnLogSheet.objects.filter(
                        batch_line_id=locked.pk,
                        layer_slot=LOGSHEET_LAYER_SLOT_SECOND,
                    ).exists()
                    locked.log_sheet_flg = 'Y' if has_first and has_second else 'N'
                locked.save(update_fields=['log_sheet_flg'])
                return row
        except IntegrityError:
            raise forms.ValidationError(
                'Could not save: this batch may already be on a log sheet, or a database constraint failed.'
            ) from None


_RM_QTY_QUANTIZE = Decimal(10) ** -QTY_DECIMAL_PLACES


class RmDispensingForm(forms.Form):
    """RM Dispensing Entry — header fields plus `lines_json` grid."""

    dispensing_dt = forms.DateField(
        label='Dispensing Date',
        error_messages={'required': 'Dispensing date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'rmDispDt'}),
    )
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select customer —',
        error_messages={'required': 'Customer is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'rmCustomer'}),
    )
    product = forms.ModelChoiceField(
        queryset=MstProd.objects.none(),
        label='Product',
        empty_label='— Select product —',
        error_messages={'required': 'Product is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'rmProduct'}),
    )
    logsheet_id = forms.IntegerField(
        label='Log sheet',
        error_messages={'required': 'Log sheet is required.', 'invalid': 'Invalid log sheet selection.'},
        widget=forms.HiddenInput(attrs={'id': 'rmLogsheetId'}),
    )
    specification = forms.ModelChoiceField(
        queryset=MstBomRmHed.objects.none(),
        label='Specification',
        empty_label='— Select specification —',
        error_messages={'required': 'Specification is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'rmSpec'}),
    )
    machine = forms.ModelChoiceField(
        queryset=MstMachine.objects.none(),
        label='Machine',
        empty_label='— Select machine —',
        error_messages={'required': 'Machine is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'rmMachine'}),
    )
    lot_no = forms.IntegerField(
        min_value=1,
        label='No. of lots',
        error_messages={'required': 'No. of lots is required.'},
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'rmLots', 'min': '1', 'step': '1'}),
    )
    dispensed_by = forms.CharField(
        max_length=150,
        label='Dispensed By',
        error_messages={'required': 'Dispensed by is required.'},
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'rmDispensedBy', 'autocomplete': 'off'}),
    )
    worker_name = forms.CharField(
        max_length=150,
        label='Worker Name',
        error_messages={'required': 'Worker name is required.'},
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'rmWorker', 'autocomplete': 'off'}),
    )
    checked_by = forms.CharField(
        required=False,
        max_length=150,
        label='Checked By',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'rmCheckedBy', 'autocomplete': 'off'}),
    )
    verified_by = forms.CharField(
        required=False,
        max_length=150,
        label='Verified By',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'rmVerifiedBy', 'autocomplete': 'off'}),
    )
    remarks = forms.CharField(
        required=False,
        max_length=100,
        label='Remarks',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'rmRemarks', 'autocomplete': 'off', 'maxlength': '100'}),
    )
    lines_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'rmLinesJson'}),
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')
        self.fields['machine'].queryset = MstMachine.objects.select_related('section').all().order_by('machine_name')
        self.fields['product'].queryset = MstProd.objects.none()
        self.fields['specification'].queryset = MstBomRmHed.objects.none()

        cust_id = None
        prod_id = None
        if self.instance:
            cust_id = getattr(self.instance, 'customer_id', None)
            prod_id = getattr(self.instance, 'product_id', None)
        else:
            raw_c = self.data.get('customer') if hasattr(self, 'data') else None
            raw_p = self.data.get('product') if hasattr(self, 'data') else None
            try:
                cust_id = int(raw_c) if raw_c else None
            except (TypeError, ValueError):
                cust_id = None
            try:
                prod_id = int(raw_p) if raw_p else None
            except (TypeError, ValueError):
                prod_id = None

        if cust_id:
            prod_ids = (
                MstCustProd.objects.filter(customer_id=cust_id)
                .values_list('product_id', flat=True)
                .distinct()
            )
            self.fields['product'].queryset = MstProd.objects.filter(prod_id__in=prod_ids).order_by('prod_name')
        if cust_id and prod_id:
            self.fields['specification'].queryset = MstBomRmHed.objects.filter(
                customer_id=cust_id,
                product_id=prod_id,
            ).order_by('-spec_id')

    def get_initial(self):
        if not self.instance:
            return {'dispensing_dt': timezone.localdate()}
        hed = self.instance
        lines = list(
            getattr(hed, 'lines', TrnlssDtl.objects.filter(dispensing=hed))
            .all()
            .order_by('dtl_id')
            .values(
                'stage_id',
                'item_id',
                'issue_qty',
                'issue_add_qty',
                'issue_date',
                'remarks',
            )
        )
        for r in lines:
            d = r.get('issue_date')
            r['issue_date'] = d.isoformat() if hasattr(d, 'isoformat') else (str(d) if d else '')
            r['issue_qty'] = str(r.get('issue_qty') or 0)
            r['issue_add_qty'] = str(r.get('issue_add_qty') or 0)
        return {
            'dispensing_dt': hed.dispensing_dt,
            'customer': hed.customer_id,
            'product': hed.product_id,
            'logsheet_id': hed.batch_line_id,
            'specification': hed.specification_id,
            'machine': hed.machine_id,
            'lot_no': hed.lot_no,
            'dispensed_by': hed.dispensed_by,
            'worker_name': hed.worker_name,
            'checked_by': hed.checked_by,
            'verified_by': hed.verified_by,
            'remarks': hed.remarks,
            'lines_json': json.dumps(
                [
                    {
                        'stage_id': int(r['stage_id']),
                        'item_id': int(r['item_id']),
                        'issue_qty': r['issue_qty'],
                        'issue_add_qty': r['issue_add_qty'],
                        'issue_date': r['issue_date'],
                        'remarks': (r.get('remarks') or ''),
                    }
                    for r in lines
                ]
            ),
        }

    def clean_dispensing_dt(self):
        d = self.cleaned_data.get('dispensing_dt')
        if d:
            try:
                validate_transaction_in_open_fy(d)
            except ValidationError as e:
                raise forms.ValidationError(list(e.messages))
            if d > timezone.localdate():
                raise forms.ValidationError('Dispensing date cannot be in the future.')
        return d

    def clean_remarks(self):
        v = (self.cleaned_data.get('remarks') or '').strip()
        return v or None

    def clean_dispensed_by(self):
        v = (self.cleaned_data.get('dispensed_by') or '').strip()
        if not v:
            raise forms.ValidationError('Dispensed by is required.')
        return v

    def clean_worker_name(self):
        v = (self.cleaned_data.get('worker_name') or '').strip()
        if not v:
            raise forms.ValidationError('Worker name is required.')
        return v

    def clean_checked_by(self):
        v = (self.cleaned_data.get('checked_by') or '').strip()
        return v or None

    def clean_verified_by(self):
        v = (self.cleaned_data.get('verified_by') or '').strip()
        return v or None

    def clean(self):
        cd = super().clean()
        cust = cd.get('customer')
        prod = cd.get('product')
        spec = cd.get('specification')
        ls_id = cd.get('logsheet_id')
        if cust and prod and not MstCustProd.objects.filter(customer=cust, product=prod).exists():
            self.add_error('product', 'This product is not linked to the selected customer.')
        if spec and cust and spec.customer_id != cust.pk:
            self.add_error('specification', 'Specification must belong to the selected customer.')
        if spec and prod and spec.product_id != prod.pk:
            self.add_error('specification', 'Specification must belong to the selected product.')

        if ls_id is not None and cust and prod:
            try:
                ls = (
                    TrnLogSheet.objects.select_related(
                        'customer',
                        'product',
                        'batch_line',
                        'batch_line__batch',
                        'batch_line__batch__customer',
                        'batch_line__batch__product',
                        'batch_line__batch__product__first_color',
                        'batch_line__batch__product__second_color',
                    )
                    .get(pk=int(ls_id))
                )
            except (TrnLogSheet.DoesNotExist, TypeError, ValueError):
                self.add_error('logsheet_id', 'Invalid log sheet.')
                return cd
            if ls.customer_id != cust.pk:
                self.add_error('logsheet_id', 'Log sheet does not belong to selected customer.')
            if ls.product_id != prod.pk:
                self.add_error('logsheet_id', 'Log sheet does not belong to selected product.')
            cd['_logsheet'] = ls
        return cd

    def clean_lines_json(self):
        raw = (self.cleaned_data.get('lines_json') or '').strip()
        if not raw or raw == '[]':
            raise forms.ValidationError('Add at least one dispensing row.')
        try:
            rows = json.loads(raw)
        except ValueError:
            raise forms.ValidationError('Invalid dispensing grid data.')
        if not isinstance(rows, list):
            raise forms.ValidationError('Invalid grid format.')
        return rows

    def _effective_batch_sizes_for_logsheet(self, ls: TrnLogSheet):
        """
        Return (batch_size_lakh, batch_size_nos) for this log sheet:
        - Single layer: full batch line quantities
        - Double layer: split quantities per slot (1/2)
        """
        bl = ls.batch_line
        if not bl:
            return Decimal('0'), Decimal('0')
        prod = getattr(ls, 'product', None) or getattr(bl.batch, 'product', None)
        layer = getattr(prod, 'tablet_layer', None) or MstProd.LAYER_SINGLE
        if layer == MstProd.LAYER_DOUBLE and ls.layer_slot in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
            n1, n2, l1, l2 = logsheet_split_batch_qty(bl.batch_qty_n, bl.batch_qty_l)
            if ls.layer_slot == LOGSHEET_LAYER_SLOT_FIRST:
                return Decimal(str(l1)), Decimal(str(n1))
            return Decimal(str(l2)), Decimal(str(n2))
        return Decimal(str(bl.batch_qty_l or 0)), Decimal(str(bl.batch_qty_n or 0))

    def _validate_and_normalize_lines(self, *, rows, spec, logsheet: TrnLogSheet):
        if not spec:
            raise forms.ValidationError('Select specification before entering dispensing.')
        if not logsheet:
            raise forms.ValidationError('Select log sheet before entering dispensing.')

        batch_size_l, _batch_size_n = self._effective_batch_sizes_for_logsheet(logsheet)
        batch_size_l = Decimal(str(batch_size_l or 0)).quantize(Decimal('0.00001'))

        bom_rows = list(
            MstBomRmDtl.objects.filter(spec_id=spec.pk)
            .select_related('stage', 'item')
            .order_by('dtl_id')
            .values('stage_id', 'item_id', 'qty')
        )
        if not bom_rows:
            raise forms.ValidationError('Selected specification has no BOM items.')

        bom_map = {}
        for r in bom_rows:
            key = (int(r['stage_id']), int(r['item_id']))
            bom_map[key] = Decimal(str(r['qty'])).quantize(_RM_QTY_QUANTIZE)

        validated = []
        seen = set()
        has_any = False
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f'Row {idx}: invalid data.')

            stage_id = row.get('stage_id')
            item_id = row.get('item_id')
            if stage_id is None or item_id is None:
                raise forms.ValidationError(f'Row {idx}: stage and item are required.')
            try:
                key = (int(stage_id), int(item_id))
            except (TypeError, ValueError):
                raise forms.ValidationError(f'Row {idx}: invalid stage or item.')
            if key in seen:
                raise forms.ValidationError(f'Row {idx}: duplicate stage + item.')
            seen.add(key)

            if key not in bom_map:
                raise forms.ValidationError(f'Row {idx}: stage/item not part of selected BOM.')

            try:
                add_qty = Decimal(str(row.get('issue_add_qty') or 0)).quantize(_RM_QTY_QUANTIZE)
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Row {idx}: additional qty must be a number.')
            if add_qty < 0:
                raise forms.ValidationError(f'Row {idx}: additional qty cannot be negative.')

            issue_date_raw = row.get('issue_date')
            issue_date = issue_date_raw if hasattr(issue_date_raw, 'year') else parse_date(str(issue_date_raw or '').strip())
            # Standard dispensing qty is auto-calculated, but date is required when any qty is recorded.
            if add_qty > 0 and not issue_date:
                raise forms.ValidationError(f'Row {idx}: dispensing date is required when quantity is entered.')

            row_remark = (row.get('remarks') or '').strip() or None
            if row_remark and len(row_remark) > 20:
                raise forms.ValidationError(f'Row {idx}: remarks must be 20 characters or fewer.')

            bom_qty = bom_map[key]
            if spec.batch_size is None or Decimal(str(spec.batch_size)) <= 0:
                raise forms.ValidationError('Invalid BOM batch size on specification.')
            qty_per_lakh = (bom_qty / Decimal(str(spec.batch_size))).quantize(_RM_QTY_QUANTIZE)

            expected = (qty_per_lakh * Decimal(str(batch_size_l))).quantize(_RM_QTY_QUANTIZE)
            issue_qty = expected  # fixed standard qty by calculation only
            if issue_qty > 0 or add_qty > 0:
                if not issue_date:
                    raise forms.ValidationError(f'Row {idx}: dispensing date is required when quantity is entered.')
                has_any = True

            validated.append({
                'stage_id': key[0],
                'item_id': key[1],
                'qty_per_lakh': qty_per_lakh,
                'issue_qty': issue_qty,
                'issue_add_qty': add_qty,
                'issue_date': issue_date or timezone.localdate(),
                'remarks': row_remark,
            })

        if not has_any:
            raise forms.ValidationError('Enter quantity in at least one dispensing row.')

        return validated

    def _compute_logsheet_rm_disp_complete(self, *, logsheet_id: int, spec_id: int) -> bool:
        required_stage_ids = set(
            MstBomRmDtl.objects.filter(spec_id=spec_id)
            .values_list('stage_id', flat=True)
            .distinct()
        )
        if not required_stage_ids:
            return False
        recorded_stage_ids = set(
            TrnlssDtl.objects.filter(
                dispensing__batch_line_id=logsheet_id,
                dispensing__specification_id=spec_id,
            )
            .filter(models.Q(issue_qty__gt=0) | models.Q(issue_add_qty__gt=0))
            .values_list('stage_id', flat=True)
            .distinct()
        )
        return required_stage_ids.issubset(recorded_stage_ids)

    def save(self):
        cd = self.cleaned_data
        logsheet = cd.get('_logsheet')
        spec = cd.get('specification')
        rows = cd.get('lines_json') or []

        lines = self._validate_and_normalize_lines(rows=rows, spec=spec, logsheet=logsheet)

        try:
            with db_transaction.atomic():
                if self.instance:
                    hed = TrnlssHed.objects.select_for_update().get(pk=self.instance.pk)
                    hed.dispensing_dt = cd['dispensing_dt']
                    hed.customer = cd['customer']
                    hed.product = cd['product']
                    hed.batch_line = logsheet
                    hed.specification = spec
                    hed.machine = cd['machine']
                    hed.lot_no = cd['lot_no']
                    hed.dispensed_by = cd['dispensed_by']
                    hed.worker_name = cd['worker_name']
                    hed.checked_by = cd.get('checked_by') or None
                    hed.verified_by = cd.get('verified_by') or None
                    hed.remarks = cd.get('remarks') or None
                    hed.save()
                else:
                    hed = TrnlssHed(
                        dispensing_dt=cd['dispensing_dt'],
                        customer=cd['customer'],
                        product=cd['product'],
                        batch_line=logsheet,
                        specification=spec,
                        machine=cd['machine'],
                        lot_no=cd['lot_no'],
                        dispensed_by=cd['dispensed_by'],
                        worker_name=cd['worker_name'],
                        checked_by=cd.get('checked_by') or None,
                        verified_by=cd.get('verified_by') or None,
                        remarks=cd.get('remarks') or None,
                    )
                    hed.save()

                for ln in lines:
                    TrnlssDtl.objects.update_or_create(
                        dispensing=hed,
                        stage_id=ln['stage_id'],
                        item_id=ln['item_id'],
                        defaults={
                            'qty_per_lakh': ln['qty_per_lakh'],
                            'issue_qty': ln['issue_qty'],
                            'issue_add_qty': ln['issue_add_qty'],
                            'issue_date': ln['issue_date'],
                            'remarks': ln['remarks'],
                        },
                    )

                # Update per-logsheet completion flag (Option A). Never blocks future dispensing.
                if logsheet and spec:
                    is_complete = self._compute_logsheet_rm_disp_complete(
                        logsheet_id=logsheet.pk,
                        spec_id=spec.pk,
                    )
                    TrnLogSheet.objects.filter(pk=logsheet.pk).update(
                        rm_disp_flg='Y' if is_complete else 'N'
                    )
                return hed
        except IntegrityError:
            raise forms.ValidationError('Could not save RM dispensing due to a database constraint.') from None
