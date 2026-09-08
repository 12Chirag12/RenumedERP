"""RM dispensing entry."""
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

from inventory.transaction_posting import (
    post_rm_dispensing_to_inventory,
    reverse_rm_dispensing_from_inventory,
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
from .shared_utils import validate_transaction_in_open_fy
from ._constants import _RM_QTY_QUANTIZE

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
            if issue_qty <= 0 and add_qty <= 0:
                continue
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
                    old_hed = TrnlssHed.objects.prefetch_related(
                        'lines__item',
                        'lines__item__item_category',
                    ).get(pk=self.instance.pk)
                    reverse_rm_dispensing_from_inventory(old_hed)
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

                TrnlssDtl.objects.filter(dispensing=hed).delete()
                for ln in lines:
                    TrnlssDtl.objects.create(
                        dispensing=hed,
                        stage_id=ln['stage_id'],
                        item_id=ln['item_id'],
                        qty_per_lakh=ln['qty_per_lakh'],
                        issue_qty=ln['issue_qty'],
                        issue_add_qty=ln['issue_add_qty'],
                        issue_date=ln['issue_date'],
                        remarks=ln['remarks'],
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
                hed = TrnlssHed.objects.prefetch_related(
                    'lines__item',
                    'lines__item__item_category',
                ).get(pk=hed.pk)
                post_rm_dispensing_to_inventory(hed)
                return hed
        except IntegrityError:
            raise forms.ValidationError('Could not save RM dispensing due to a database constraint.') from None
