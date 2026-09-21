"""Batch allocation from sales order line."""
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
from .shared_utils import _parse_mmm_yyyy, _parse_month_any, _ym_key
from ._constants import _BATCH_L_QUANTIZE, _BATCH_N_QUANTIZE, _QTY_QUANTIZE, _SO_QTY_QUANTIZE


def _batch_allocation_required_qty_n(line):
    return Decimal(str(line.no_of_tablets or 0)).quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)


def _batch_allocation_allocated_qty_n(line):
    allocated = line.batch_headers.aggregate(total=models.Sum('lines__batch_qty_n'))['total']
    return Decimal(str(allocated or 0)).quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)


def batch_allocation_remaining_qty(line):
    required_n = _batch_allocation_required_qty_n(line)
    allocated_n = _batch_allocation_allocated_qty_n(line)
    remaining_n = max(required_n - allocated_n, Decimal('0'))
    remaining_n = remaining_n.quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)
    return (
        (remaining_n / Decimal('100000')).quantize(_BATCH_L_QUANTIZE, rounding=ROUND_HALF_UP),
        remaining_n,
    )

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

        remaining_qty_l, remaining_qty_n = batch_allocation_remaining_qty(line)
        if remaining_qty_l <= 0:
            self.add_error('order_line_id', 'This line is already completed.')
            return cd

        order_qty_l = remaining_qty_l
        order_qty_n = remaining_qty_n
        if order_qty_l <= 0:
            self.add_error('order_line_id', 'Remaining quantity (Lacs) must be greater than zero.')
            return cd

        try:
            cust_prod = MstCustProd.objects.get(customer=cust, product=product)
        except MstCustProd.DoesNotExist:
            self.add_error(
                'order_line_id',
                'Link this product to the customer on the Customer master and set a 3-character batch abbreviation (letters or symbols).',
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

        count = int((target_n + bsn - 1) // bsn)
        allocated_n = [bsn] * (count - 1)
        allocated_n.append(target_n - (bsn * (count - 1)))
        if allocated_n[-1] <= 0 or allocated_n[-1] > bsn:
            self.add_error('batch_size_n', 'Generated batch quantities do not fit the selected batch size.')
            return cd

        existing_numbers = TrnBatchDtl.objects.filter(
            batch__batch_abbr=abbr,
        ).values_list('batch_no', flat=True)
        max_seq = 0
        for batch_no in existing_numbers:
            match = re.fullmatch(rf'{re.escape(abbr)}(\d+)', batch_no or '')
            if match:
                max_seq = max(max_seq, int(match.group(1)))
        batch_from = max_seq + 1
        batch_to = batch_from + count - 1

        lines = []
        batch_nos = []
        for offset, qn in enumerate(allocated_n):
            seq = batch_from + offset
            ql = (qn / Decimal('100000')).quantize(_BATCH_L_QUANTIZE)
            bn = f'{abbr}{seq}'
            if len(bn) > 15:
                self.add_error('batch_size_l', 'Generated batch number would exceed 15 characters.')
                return cd
            batch_nos.append(bn)
            lines.append({
                'batch_no': bn,
                'batch_qty_l': ql,
                'batch_qty_n': qn,
            })

        dup_exists = TrnBatchDtl.objects.filter(batch_no__in=batch_nos).exists()
        if dup_exists:
            self.add_error('batch_size_l', 'Generated batch number already exists.')

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
            'batch_from': batch_from,
            'batch_to': batch_to,
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
                locked_remaining_l, _locked_remaining_n = batch_allocation_remaining_qty(locked_line)
                if locked_remaining_l <= 0:
                    raise forms.ValidationError({'order_line_id': 'This line is already completed.'})

                alloc_l = ctx['partial_qty_l'] if ctx['partial_yn'] == 'Y' else locked_remaining_l
                alloc_l = Decimal(str(alloc_l)).quantize(_BATCH_L_QUANTIZE)
                if alloc_l <= 0:
                    raise forms.ValidationError({'partial_qty_l': 'Allocation quantity must be greater than zero.'})
                if alloc_l > locked_remaining_l:
                    raise forms.ValidationError({'partial_qty_l': 'Allocation exceeds remaining quantity.'})
                generated_n = sum((row['batch_qty_n'] for row in lines), Decimal('0'))
                expected_n = (alloc_l * Decimal('100000')).quantize(_BATCH_N_QUANTIZE, rounding=ROUND_HALF_UP)
                if generated_n != expected_n:
                    raise forms.ValidationError(
                        {'batch_size_l': 'Batch preview is out of date. Please review the remaining quantity and try again.'}
                    )

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
                new_rem = (locked_remaining_l - alloc_l).quantize(_BATCH_L_QUANTIZE, rounding=ROUND_HALF_UP)
                if new_rem < 0:
                    new_rem = Decimal('0').quantize(_BATCH_L_QUANTIZE)
                locked_line.is_completed = (new_rem == 0)
                locked_line.save(update_fields=['is_completed'])
                return hed
        except IntegrityError:
            raise forms.ValidationError(
                'Batch already exists or a database constraint failed.'
            ) from None
