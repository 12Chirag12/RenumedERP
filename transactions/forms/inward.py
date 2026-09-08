"""Inward (GRN) and related helpers."""
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

from inventory.transaction_posting import post_inward_to_inventory, reverse_inward_from_inventory

from ..constants import (
    GRN_CATEGORY_IDS,
    GRN_NO_PATTERN,
    GST_TYPE_EXEMPTED,
    GST_TYPE_IGST,
    GST_TYPE_IDS,
    QTY_DECIMAL_PLACES,
    REGISTER_NO_PATTERN,
    SO_QTY_DECIMAL_PLACES,
)
from ..models import (
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
from .shared_utils import (
    _delete_media_relative,
    _safe_filename_token,
    suggested_register_no,
    validate_transaction_in_open_fy,
)
from ._constants import (
    HEADER_DOC_EXTENSIONS,
    HEADER_DOC_MAX_BYTES,
    GRN_NO_RE,
    REGISTER_NO_RE,
    _MONEY_QUANTIZE,
    _QTY_QUANTIZE,
)

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
                'pkg_style': d1.pkg_style,
                'qty': str(d1.quantity),
                'rate': str(d1.rate),
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
            pkg_style = row.get('pkg_style')
            qty_raw = row.get('qty')
            rate_raw = row.get('rate')
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

            try:
                if rate_raw in (None, ''):
                    rate = Decimal('0')
                else:
                    rate = Decimal(str(rate_raw))
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Line {idx}: rate must be a number.')
            rate = rate.quantize(_MONEY_QUANTIZE)
            if rate < 0:
                raise forms.ValidationError(f'Line {idx}: rate cannot be negative.')
            maintain_batch = item.maintain_batch == 'Y'
            if not maintain_batch:
                if batches_raw:
                    raise forms.ValidationError(
                        f'Line {idx}: batches are not allowed for "{item.item_name}" '
                        '(Maintain Batches is No on the item).'
                    )
                validated.append({
                    'item': item,
                    'pkg_style': pkg_style,
                    'qty': qty,
                    'rate': rate,
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
                'pkg_style': pkg_style,
                'qty': qty,
                'rate': rate,
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
                    old_hed = TrnInwHed.objects.prefetch_related(
                        'lines__item',
                        'batch_lines',
                    ).get(pk=self.instance.pk)
                    reverse_inward_from_inventory(old_hed)
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
                        pkg_style=line['pkg_style'],
                        quantity=line['qty'],
                        uom=line['uom'],
                        rate=line['rate'],
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
                for line in lines:
                    MstItem.objects.filter(pk=line['item'].pk).update(
                        last_purchase_rate=line['rate'],
                    )
                hed = TrnInwHed.objects.prefetch_related(
                    'lines__item',
                    'batch_lines',
                ).get(pk=hed.pk)
                post_inward_to_inventory(hed)
                return hed
        except IntegrityError:
            raise forms.ValidationError(
                'Could not save: duplicate register number or GRN number, or a database constraint failed.'
            ) from None

