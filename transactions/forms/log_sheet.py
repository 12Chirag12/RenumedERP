"""Granulation log sheet entry."""
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
    _granulation_section_key,
    _parse_mmm_yyyy,
    _ym_key,
    validate_transaction_in_open_fy,
)

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
