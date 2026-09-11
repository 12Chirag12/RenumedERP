"""Sales order entry form."""
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
    validate_transaction_in_open_fy,
)
from ._constants import (
    HEADER_DOC_EXTENSIONS,
    HEADER_DOC_MAX_BYTES,
    _BATCH_N_QUANTIZE,
    _MONEY_QUANTIZE,
    _SO_QTY_QUANTIZE,
)

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
        label='Packing / forwarding',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'soPkgFwd', 'step': '0.01', 'min': '0'}),
    )
    frieght_amt = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Freight',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'soFreight', 'step': '0.01', 'min': '0'}),
    )
    oth_charges = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Other charges',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'soOthCharges', 'step': '0.01', 'min': '0'}),
    )
    round_off = forms.DecimalField(
        required=False,
        max_digits=6,
        decimal_places=2,
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
