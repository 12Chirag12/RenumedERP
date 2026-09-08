"""Daily packing (contractors) — TrnPkgCont entry form."""

from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.utils import timezone

from masters.models import MstCust, MstOperator, MstPkgStyle, MstProd

from ..models import TrnLogSheet, TrnPkgCont
from .shared_utils import validate_transaction_in_open_fy


def _contractor_queryset():
    return MstOperator.objects.filter(designation__iexact='Contractor').order_by('opt_name')


class PkgContForm(forms.Form):
    pkgcont_date = forms.DateField(
        label='Packing date',
        error_messages={'required': 'Packing date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'pcPkgDate'}),
    )
    contractor = forms.ModelChoiceField(
        queryset=MstOperator.objects.none(),
        label='Contractor',
        empty_label='— Select contractor —',
        error_messages={'required': 'Contractor is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'pcContractor'}),
    )
    no_of_girls = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=9999,
        label='No. of girls',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'pcGirls', 'min': '0', 'max': '9999', 'step': '1'}),
    )
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.all().order_by('cust_name'),
        label='Customer',
        empty_label='— Select customer —',
        error_messages={'required': 'Customer is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'pcCustomer'}),
    )
    product = forms.ModelChoiceField(
        queryset=MstProd.objects.none(),
        label='Product',
        empty_label='— Select product —',
        error_messages={'required': 'Product is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'pcProduct'}),
    )
    logsheet_id = forms.IntegerField(
        label='Log sheet',
        error_messages={'required': 'Batch / log sheet is required.', 'invalid': 'Invalid log sheet selection.'},
        widget=forms.HiddenInput(attrs={'id': 'pcLogsheetId'}),
    )
    pkg_style = forms.ModelChoiceField(
        queryset=MstPkgStyle.objects.none(),
        label='Packing style',
        empty_label='— Select packing style —',
        error_messages={'required': 'Packing style is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'pcPkgStyle'}),
    )
    shipper_no = forms.IntegerField(
        min_value=1,
        max_value=999999,
        label='Shipper no.',
        error_messages={'required': 'Shipper number is required.'},
        widget=forms.NumberInput(
            attrs={'class': 'cu-input cu-num', 'id': 'pcShipper', 'min': '1', 'max': '999999', 'step': '1'},
        ),
    )
    qty_nos = forms.DecimalField(
        max_digits=12,
        decimal_places=0,
        min_value=Decimal('1'),
        label='Qty (nos.)',
        error_messages={'required': 'Quantity (nos.) is required.'},
        widget=forms.TextInput(attrs={'class': 'cu-input cu-num', 'id': 'pcQtyNos', 'inputmode': 'numeric', 'autocomplete': 'off'}),
    )
    qty_loose = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=0,
        min_value=Decimal('0'),
        label='Qty (loose)',
        widget=forms.TextInput(attrs={'class': 'cu-input cu-num', 'id': 'pcQtyLoose', 'inputmode': 'numeric', 'autocomplete': 'off'}),
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={'class': 'cu-input cu-textarea', 'id': 'pcRemarks', 'rows': 2, 'maxlength': '2000'},
        ),
        label='Remarks',
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['contractor'].queryset = _contractor_queryset()
        self.fields['product'].queryset = MstProd.objects.none()
        self.fields['pkg_style'].queryset = MstPkgStyle.objects.none()

        cust_id = None
        prod_id = None
        if self.instance:
            ls = self.instance.log_sheet
            if ls:
                cust_id = ls.customer_id
                prod_id = ls.product_id
        else:
            try:
                cust_id = int(self.data.get('customer')) if self.data.get('customer') else None
            except (TypeError, ValueError):
                cust_id = None
            try:
                prod_id = int(self.data.get('product')) if self.data.get('product') else None
            except (TypeError, ValueError):
                prod_id = None

        if cust_id:
            prod_ids = (
                TrnLogSheet.objects.filter(customer_id=cust_id)
                .values_list('product_id', flat=True)
                .distinct()
            )
            self.fields['product'].queryset = MstProd.objects.filter(prod_id__in=prod_ids).order_by('prod_name')
        if prod_id:
            try:
                pt = MstProd.objects.only('prod_type_id').get(pk=prod_id).prod_type_id
            except MstProd.DoesNotExist:
                pt = None
            if pt:
                self.fields['pkg_style'].queryset = (
                    MstPkgStyle.objects.filter(pkg_type_id=pt).order_by('pkg_style_name')
                )

    def get_initial(self):
        if not self.instance:
            return {'pkgcont_date': timezone.localdate()}
        ls = self.instance.log_sheet
        return {
            'pkgcont_date': self.instance.pkgcont_date,
            'contractor': self.instance.contractor_id,
            'no_of_girls': self.instance.no_of_girls,
            'customer': ls.customer_id if ls else None,
            'product': ls.product_id if ls else None,
            'logsheet_id': ls.logsheet_id if ls else None,
            'pkg_style': self.instance.pkg_style_id,
            'shipper_no': self.instance.shipper_no,
            'qty_nos': self.instance.qty_nos,
            'qty_loose': self.instance.qty_loose,
            'remarks': self.instance.remarks or '',
        }

    def clean_pkgcont_date(self):
        d = self.cleaned_data.get('pkgcont_date')
        if d:
            try:
                validate_transaction_in_open_fy(d)
            except ValidationError as e:
                raise forms.ValidationError(list(e.messages))
            if d > timezone.localdate():
                raise forms.ValidationError('Packing date cannot be in the future.')
        return d

    def clean_qty_loose(self):
        raw = self.cleaned_data.get('qty_loose')
        if raw in (None, ''):
            return None
        try:
            d = raw if isinstance(raw, Decimal) else Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError, ArithmeticError):
            raise forms.ValidationError('Enter a valid quantity.')
        if d < 0:
            raise forms.ValidationError('Loose quantity cannot be negative.')
        return d.quantize(Decimal('1'))

    def clean_qty_nos(self):
        raw = self.cleaned_data.get('qty_nos')
        if raw in (None, ''):
            raise forms.ValidationError('Quantity (nos.) is required.')
        try:
            d = raw if isinstance(raw, Decimal) else Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError, ArithmeticError):
            raise forms.ValidationError('Enter a valid quantity.')
        if d < 1:
            raise forms.ValidationError('Quantity (nos.) must be greater than zero.')
        return d.quantize(Decimal('1'))

    def clean_remarks(self):
        v = (self.cleaned_data.get('remarks') or '').strip()
        return v or None

    def clean(self):
        cd = super().clean()
        cust = cd.get('customer')
        prod = cd.get('product')
        ls_id = cd.get('logsheet_id')
        contractor = cd.get('contractor')
        pkg_style = cd.get('pkg_style')
        pdate = cd.get('pkgcont_date')

        if contractor and not _contractor_queryset().filter(pk=contractor.pk).exists():
            self.add_error('contractor', 'Select an operator with designation Contractor.')

        if ls_id is not None and cust and prod:
            try:
                ls = (
                    TrnLogSheet.objects.select_related('customer', 'product', 'batch_line')
                    .get(pk=int(ls_id))
                )
            except (TrnLogSheet.DoesNotExist, TypeError, ValueError):
                self.add_error('logsheet_id', 'Invalid log sheet / batch.')
                return cd
            if ls.customer_id != cust.pk:
                self.add_error('logsheet_id', 'Log sheet does not belong to the selected customer.')
            if ls.product_id != prod.pk:
                self.add_error('logsheet_id', 'Log sheet does not belong to the selected product.')
            cd['_logsheet'] = ls

            if pkg_style and prod and pkg_style.pkg_type_id != prod.prod_type_id:
                self.add_error('pkg_style', 'Packing style must match the selected product type.')

            if pdate and contractor and pkg_style and ls:
                dup = TrnPkgCont.objects.filter(
                    pkgcont_date=pdate,
                    log_sheet=ls,
                    contractor=contractor,
                    pkg_style=pkg_style,
                )
                if self.instance:
                    dup = dup.exclude(pk=self.instance.pk)
                if dup.exists():
                    self.add_error(
                        None,
                        'An entry already exists for this date, batch, contractor, and packing style.',
                    )
        return cd

    @db_transaction.atomic
    def save(self):
        cd = self.cleaned_data
        ls = cd['_logsheet']
        vals = {
            'pkgcont_date': cd['pkgcont_date'],
            'contractor': cd['contractor'],
            'no_of_girls': cd.get('no_of_girls'),
            'log_sheet': ls,
            'pkg_style': cd['pkg_style'],
            'shipper_no': cd['shipper_no'],
            'qty_nos': cd['qty_nos'],
            'qty_loose': cd.get('qty_loose'),
            'remarks': cd.get('remarks'),
        }
        try:
            if self.instance:
                for k, v in vals.items():
                    setattr(self.instance, k, v)
                self.instance.save()
                return self.instance
            return TrnPkgCont.objects.create(**vals)
        except IntegrityError:
            raise forms.ValidationError(
                'Could not save: duplicate or invalid reference. Check date, batch, contractor, and packing style.',
            )
