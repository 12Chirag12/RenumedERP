"""
Daily Production Report (DPR) — TrnDPR entry form.

Business rules align with Daily Production Report (DPR) – Tab.txt:
flow (section → date → machine → shift → customer → SO products → log-sheet batch → spec),
machine not-working minimal capture, and validations.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from masters.models import (
    MstBomRmHed,
    MstCust,
    MstCustProd,
    MstMachine,
    MstOperator,
    MstProd,
    MstSection,
)

from ..models import (
    DPR_MACHINE_NOT_WORKING,
    DPR_MACHINE_STATUS_CHOICES,
    DPR_MACHINE_WORKING,
    DPR_SHIFT_CHOICES,
    TrnBatchDtl,
    TrnDpr,
    TrnDprInputBatch,
    TrnLogSheet,
    TrnSlsOrdDtl1,
)
from .shared_utils import dpr_is_multi_batch_section, validate_transaction_in_open_fy

from inventory.transaction_posting import post_dpr_production_to_inventory, reverse_dpr_production_from_inventory


def _time_to_minutes(t) -> int:
    return t.hour * 60 + t.minute


def _dpr_interval_minutes(start_t, end_t) -> tuple[int, int]:
    """Map start/end times to [s, e) on a 48h line (minutes from midnight of DPR date)."""
    s = _time_to_minutes(start_t)
    e = _time_to_minutes(end_t)
    if e <= s:
        e += 24 * 60
    return s, e


def _intervals_overlap(s1: int, e1: int, s2: int, e2: int) -> bool:
    return max(s1, s2) < min(e1, e2)


def dpr_format_total_time(start_t, end_t) -> str:
    s, e = _dpr_interval_minutes(start_t, end_t)
    mins = e - s
    h, m = divmod(mins, 60)
    return f'{h:02d}:{m:02d} Hrs.'


def _parse_dpr_log_sheet_ids_json(raw) -> list[int]:
    """Parse JSON array of log sheet PKs from the multi-batch hidden field."""
    if raw is None:
        return []
    if isinstance(raw, list):
        data = raw
    else:
        s = str(raw).strip()
        if not s:
            return []
        try:
            data = json.loads(s)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError('Invalid batch selection data.') from exc
    if not isinstance(data, list):
        raise forms.ValidationError('Invalid batch selection format.')
    out: list[int] = []
    for x in data:
        try:
            out.append(int(x))
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError('Invalid log sheet id in selection.') from exc
    return list(dict.fromkeys(out))


def _sync_dpr_input_batches(row: TrnDpr, log_sheet_ids: list[int]) -> None:
    row.input_batches.all().delete()
    if not log_sheet_ids:
        return
    TrnDprInputBatch.objects.bulk_create(
        [TrnDprInputBatch(dpr=row, log_sheet_id=lsid) for lsid in log_sheet_ids]
    )


def _mark_logsheets_for_dpr_multi(row: TrnDpr) -> None:
    ls_ids = list(row.input_batches.values_list('log_sheet_id', flat=True))
    if ls_ids:
        TrnLogSheet.objects.filter(pk__in=ls_ids).update(dpr_flg='Y')


class DprForm(forms.Form):
    trn_dpr_dt = forms.DateField(
        label='DPR date',
        error_messages={'required': 'DPR date is required.'},
        widget=forms.DateInput(attrs={'class': 'cu-input', 'type': 'date', 'id': 'dprDt'}),
    )
    section = forms.ModelChoiceField(
        queryset=MstSection.objects.none(),
        label='Section',
        empty_label='— Select section —',
        error_messages={'required': 'Section is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'dprSection'}),
    )
    machine = forms.ModelChoiceField(
        queryset=MstMachine.objects.none(),
        label='Machine',
        empty_label='— Select machine —',
        error_messages={'required': 'Machine is required.'},
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'dprMachine'}),
    )
    machine_working = forms.ChoiceField(
        label='Machine status',
        choices=DPR_MACHINE_STATUS_CHOICES,
        initial=DPR_MACHINE_WORKING,
        widget=forms.Select(attrs={'class': 'cu-select', 'id': 'dprMachineWorking'}),
    )
    shift = forms.ChoiceField(
        label='Shift',
        choices=DPR_SHIFT_CHOICES,
        error_messages={'required': 'Shift is required.'},
        widget=forms.Select(attrs={'class': 'cu-select', 'id': 'dprShift'}),
    )

    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        required=False,
        empty_label='— Select customer —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'dprCustomer'}),
    )
    product = forms.ModelChoiceField(
        queryset=MstProd.objects.none(),
        label='Product',
        required=False,
        empty_label='— Select product —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'dprProduct'}),
    )

    batch_dtl_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'dprBatchDtlId'}),
    )
    log_sheet_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'dprLogSheetId'}),
    )
    specification_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'dprSpecId'}),
    )
    log_sheet_ids = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'dprLogSheetIdsJson'}),
    )
    batch_size_lakh = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=5,
        min_value=Decimal('0'),
        label='Batch size (Lakh)',
        widget=forms.TextInput(
            attrs={
                'class': 'cu-input cu-num',
                'id': 'dprBatchSizeLakh',
                'inputmode': 'decimal',
                'autocomplete': 'off',
                'placeholder': 'e.g. 2.5',
            },
        ),
    )

    batch_rem = forms.CharField(
        required=False,
        max_length=30,
        label='Batch remarks',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'id': 'dprBatchRem', 'maxlength': '30', 'autocomplete': 'off'}),
    )
    lot_no = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=9999,
        label='Lot nos.',
        widget=forms.NumberInput(attrs={'class': 'cu-input cu-num', 'id': 'dprLotNo', 'min': '0', 'max': '9999'}),
    )
    qty_kg = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0'),
        label='Qty (kg)',
        widget=forms.TextInput(attrs={'class': 'cu-input cu-num', 'id': 'dprQtyKg', 'inputmode': 'decimal', 'autocomplete': 'off'}),
    )
    qty_nos = forms.IntegerField(
        required=False,
        min_value=0,
        label='Qty (nos.)',
        widget=forms.NumberInput(attrs={'class': 'cu-input cu-num', 'id': 'dprQtyNos', 'min': '0', 'autocomplete': 'off'}),
    )
    section_qty = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        label='Section qty',
        widget=forms.TextInput(attrs={'class': 'cu-input cu-num', 'id': 'dprSectionQty', 'inputmode': 'decimal', 'autocomplete': 'off'}),
    )

    start_time = forms.TimeField(
        label='Start time',
        widget=forms.TimeInput(attrs={'class': 'cu-input', 'type': 'time', 'id': 'dprStartTime'}),
    )
    end_time = forms.TimeField(
        label='End time',
        widget=forms.TimeInput(attrs={'class': 'cu-input', 'type': 'time', 'id': 'dprEndTime'}),
    )

    operators = forms.ModelMultipleChoiceField(
        queryset=MstOperator.objects.none(),
        required=False,
        label='Operators',
        widget=forms.SelectMultiple(attrs={'class': 'cu-select searchable-dropdown', 'id': 'dprOperators'}),
    )
    no_of_helper = forms.IntegerField(
        min_value=0,
        max_value=999,
        label='No. of helpers',
        widget=forms.NumberInput(attrs={'class': 'cu-input cu-num', 'id': 'dprHelpers', 'min': '0', 'max': '999'}),
    )
    remarks = forms.CharField(
        required=False,
        max_length=500,
        label='Remarks',
        widget=forms.Textarea(attrs={'class': 'cu-textarea', 'id': 'dprRemarks', 'rows': '1', 'maxlength': '500'}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self._instance = instance
        inst_initial = {}
        if instance:
            inst_initial['trn_dpr_dt'] = instance.trn_dpr_dt
            inst_initial['section'] = instance.section_id
            inst_initial['machine'] = instance.machine_id
            inst_initial['shift'] = instance.shift_id
            inst_initial['machine_working'] = instance.machine_working
            if instance.customer_id:
                inst_initial['customer'] = instance.customer_id
            if instance.product_id:
                inst_initial['product'] = instance.product_id
            if instance.batch_line_id:
                inst_initial['batch_dtl_id'] = instance.batch_line_id
            if instance.log_sheet_id:
                inst_initial['log_sheet_id'] = instance.log_sheet_id
            if (
                not instance.batch_line_id
                and instance.machine_working == DPR_MACHINE_WORKING
                and dpr_is_multi_batch_section(instance.section)
            ):
                ib = list(instance.input_batches.values_list('log_sheet_id', flat=True).order_by('input_id'))
                if ib:
                    inst_initial['log_sheet_ids'] = json.dumps(ib)
            if instance.batch_size_lakh is not None:
                inst_initial['batch_size_lakh'] = instance.batch_size_lakh
            if instance.specification_id:
                inst_initial['specification_id'] = instance.specification_id
            inst_initial['batch_rem'] = instance.batch_rem or ''
            inst_initial['lot_no'] = instance.lot_no
            inst_initial['qty_kg'] = instance.qty_kg
            inst_initial['qty_nos'] = int(instance.qty_nos)
            if instance.section_qty is not None:
                inst_initial['section_qty'] = instance.section_qty
            inst_initial['start_time'] = instance.start_time
            inst_initial['end_time'] = instance.end_time
            operator_ids = list(instance.operators.values_list('pk', flat=True))
            if not operator_ids:
                operator_ids = [operator_id for operator_id in (instance.operator1_id, instance.operator2_id) if operator_id]
            inst_initial['operators'] = operator_ids
            inst_initial['no_of_helper'] = instance.no_of_helper
            inst_initial['remarks'] = instance.remarks or ''

        user_initial = kwargs.pop('initial', None) or {}
        merged_initial = {**inst_initial, **user_initial}
        if 'log_sheet_ids' not in merged_initial:
            merged_initial['log_sheet_ids'] = '[]'
        kwargs['initial'] = merged_initial
        super().__init__(*args, **kwargs)
        self.fields['section'].queryset = MstSection.objects.all().order_by('section_name')
        self.fields['machine'].queryset = MstMachine.objects.select_related('section').order_by('machine_name')
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')
        self.fields['product'].queryset = MstProd.objects.all().order_by('prod_name')

        sec = None
        if self.data:
            raw_sec = self.data.get('section')
            if raw_sec:
                try:
                    sec = MstSection.objects.get(pk=int(raw_sec))
                except (ValueError, TypeError, MstSection.DoesNotExist):
                    sec = None
        elif instance and instance.section_id:
            sec = instance.section
        elif merged_initial.get('section'):
            try:
                sec = MstSection.objects.get(pk=int(merged_initial['section']))
            except (ValueError, TypeError, MstSection.DoesNotExist):
                sec = None
        op_qs = (
            MstOperator.objects.filter(section_links__section=sec).distinct().order_by('opt_name')
            if sec
            else MstOperator.objects.none()
        )
        self.fields['operators'].queryset = op_qs

    def clean_trn_dpr_dt(self):
        d = self.cleaned_data.get('trn_dpr_dt')
        if d:
            try:
                validate_transaction_in_open_fy(d)
            except ValidationError as e:
                raise forms.ValidationError(list(e.messages))
            if d > timezone.localdate():
                raise forms.ValidationError('DPR date cannot be in the future.')
        return d

    def clean_machine(self):
        machine = self.cleaned_data.get('machine')
        section = self.cleaned_data.get('section')
        if machine and section and machine.section_id != section.pk:
            raise forms.ValidationError('Machine must belong to the selected section.')
        return machine

    def clean(self):
        cd = super().clean()
        working = (cd.get('machine_working') or DPR_MACHINE_WORKING) == DPR_MACHINE_WORKING
        sec = cd.get('section')

        if not sec:
            return cd

        if not working:
            if not cd.get('start_time') or not cd.get('end_time'):
                self.add_error('start_time', 'Start and end times are required when the machine is not working.')
            else:
                st, et = cd['start_time'], cd['end_time']
                if st == et:
                    self.add_error('end_time', 'Start and end time cannot be identical.')
                else:
                    self._validate_times_overlap(cd)
            return cd

        cust = cd.get('customer')
        prod = cd.get('product')
        if not cust:
            self.add_error('customer', 'Customer is required when the machine is working.')
        if not prod:
            self.add_error('product', 'Product is required when the machine is working.')
        if not cust or not prod:
            return cd

        if not MstCustProd.objects.filter(customer=cust, product=prod).exists():
            self.add_error('product', 'This product is not linked to the selected customer.')
        if not TrnSlsOrdDtl1.objects.filter(order__customer_id=cust.pk, product=prod).exists():
            self.add_error('product', 'This product has no sales order line for the selected customer.')
        if self.has_error('product'):
            return cd

        if dpr_is_multi_batch_section(sec):
            return self._clean_working_multi_batch(cd)
        return self._clean_working_single_batch(cd)

    def _clean_working_multi_batch(self, cd):
        cust, prod = cd['customer'], cd['product']
        try:
            id_list = _parse_dpr_log_sheet_ids_json(cd.get('log_sheet_ids'))
        except forms.ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, 'messages', None) else (str(exc.args[0]) if exc.args else str(exc))
            self.add_error('log_sheet_ids', msg)
            return cd

        if len(id_list) < 1:
            self.add_error('log_sheet_ids', 'Select at least one log sheet row (batch / colour).')
            return cd

        log_rows = list(
            TrnLogSheet.objects.select_related('batch_line', 'batch_line__batch', 'batch_line__batch__customer').filter(
                pk__in=id_list
            )
        )
        by_id = {ls.pk: ls for ls in log_rows}
        if len(by_id) != len(id_list):
            self.add_error('log_sheet_ids', 'One or more selected log sheet rows are invalid.')
            return cd
        ordered_ls = [by_id[pid] for pid in id_list]

        for ls in ordered_ls:
            if ls.customer_id != cust.pk:
                self.add_error('log_sheet_ids', 'Every log sheet row must belong to the selected customer.')
                return cd
            if ls.product_id != prod.pk:
                self.add_error('log_sheet_ids', 'Every log sheet row must belong to the selected product.')
                return cd
            bl = ls.batch_line
            if bl.batch.customer_id != cust.pk or bl.batch.product_id != prod.pk:
                self.add_error('log_sheet_ids', 'Batch on a log sheet row does not match customer / product.')
                return cd

        spk = cd.get('specification_id')
        if spk is None:
            self.add_error('specification_id', 'Specification is required.')
            return cd
        try:
            spec = MstBomRmHed.objects.get(pk=int(spk))
        except (MstBomRmHed.DoesNotExist, TypeError, ValueError):
            self.add_error('specification_id', 'Invalid specification.')
            return cd
        if spec.customer_id != cust.pk or spec.product_id != prod.pk:
            self.add_error('specification_id', 'Specification must belong to the selected customer and product.')

        bsl = cd.get('batch_size_lakh')
        if bsl is None or bsl <= 0:
            self.add_error('batch_size_lakh', 'Batch size (Lakh) must be greater than zero.')

        lot = cd.get('lot_no')
        if lot is None or int(lot) < 1:
            self.add_error('lot_no', 'Lot nos. must be greater than zero.')

        qty_kg = cd.get('qty_kg')
        qty_nos = cd.get('qty_nos')
        if qty_kg is None or qty_kg <= 0:
            self.add_error('qty_kg', 'Qty (kg) must be greater than zero.')
        if qty_nos is None or int(qty_nos) < 1:
            self.add_error('qty_nos', 'Qty (nos.) must be greater than zero.')

        if not cd.get('operators'):
            self.add_error('operators', 'Select at least one operator.')

        cd['_multi_log_sheet_ids'] = id_list
        cd['_multi_batch_lines'] = None
        cd['_batch_line'] = None
        cd['_log_sheet'] = None
        cd['_spec'] = spec
        self._validate_times_overlap(cd)
        return cd

    def _clean_working_single_batch(self, cd):
        cust, prod = cd['customer'], cd['product']
        bpk = cd.get('batch_dtl_id')
        lpk = cd.get('log_sheet_id')
        spk = cd.get('specification_id')

        if bpk is None:
            self.add_error('batch_dtl_id', 'Select a batch that has a log sheet.')
            return cd
        try:
            line = TrnBatchDtl.objects.select_related('batch', 'batch__product', 'batch__customer', 'batch__order').get(
                pk=int(bpk)
            )
        except (TrnBatchDtl.DoesNotExist, TypeError, ValueError):
            self.add_error('batch_dtl_id', 'Invalid batch allocation line.')
            return cd

        if cust and line.batch.customer_id != cust.pk:
            self.add_error('batch_dtl_id', 'Batch does not belong to the selected customer.')
        if prod and line.batch.product_id != prod.pk:
            self.add_error('batch_dtl_id', 'Batch does not belong to the selected product.')

        if not TrnLogSheet.objects.filter(batch_line=line).exists():
            self.add_error('batch_dtl_id', 'A log sheet must exist for this batch before DPR entry.')

        if lpk is None:
            self.add_error('log_sheet_id', 'Select the log sheet row (batch / colour slot) for this DPR.')
            return cd
        try:
            ls = TrnLogSheet.objects.select_related('batch_line').get(pk=int(lpk))
        except (TrnLogSheet.DoesNotExist, TypeError, ValueError):
            self.add_error('log_sheet_id', 'Invalid log sheet selection.')
            return cd
        if ls.batch_line_id != line.pk:
            self.add_error('log_sheet_id', 'Log sheet does not match the selected batch.')

        if spk is None:
            self.add_error('specification_id', 'Specification is required.')
            return cd
        try:
            spec = MstBomRmHed.objects.get(pk=int(spk))
        except (MstBomRmHed.DoesNotExist, TypeError, ValueError):
            self.add_error('specification_id', 'Invalid specification.')
            return cd
        if spec.customer_id != cust.pk or spec.product_id != prod.pk:
            self.add_error('specification_id', 'Specification must belong to the selected customer and product.')

        lot = cd.get('lot_no')
        if lot is None or int(lot) < 1:
            self.add_error('lot_no', 'Lot nos. must be greater than zero.')

        qty_kg = cd.get('qty_kg')
        qty_nos = cd.get('qty_nos')
        if qty_kg is None or qty_kg <= 0:
            self.add_error('qty_kg', 'Qty (kg) must be greater than zero.')
        if qty_nos is None or int(qty_nos) < 1:
            self.add_error('qty_nos', 'Qty (nos.) must be greater than zero.')

        if not cd.get('operators'):
            self.add_error('operators', 'Select at least one operator.')

        used_qs = TrnDpr.objects.filter(batch_line=line, machine_working=DPR_MACHINE_WORKING)
        if self._instance and getattr(self._instance, 'pk', None):
            used_qs = used_qs.exclude(pk=self._instance.pk)
        used_n = used_qs.aggregate(s=Sum('qty_nos'))['s'] or 0
        cap_n = int(line.batch_qty_n) if line.batch_qty_n is not None else 0
        if cap_n > 0 and int(qty_nos) + int(used_n) > cap_n:
            self.add_error(
                'qty_nos',
                f'Total DPR quantity in nos. for this batch cannot exceed batch size ({cap_n}).',
            )

        cd['_multi_batch_lines'] = None
        cd['_multi_log_sheet_ids'] = None
        cd['_batch_line'] = line
        cd['_log_sheet'] = ls
        cd['_spec'] = spec
        self._validate_times_overlap(cd)
        return cd

    def _validate_times_overlap(self, cd):
        st = cd.get('start_time')
        et = cd.get('end_time')
        machine = cd.get('machine')
        dpr_dt = cd.get('trn_dpr_dt')
        if not st or not et or not machine or not dpr_dt:
            return
        if st == et:
            self.add_error('end_time', 'Start and end time cannot be identical.')
            return

        s1, e1 = _dpr_interval_minutes(st, et)

        qs = TrnDpr.objects.filter(machine=machine, trn_dpr_dt=dpr_dt)
        if self._instance and getattr(self._instance, 'pk', None):
            qs = qs.exclude(pk=self._instance.pk)
        for row in qs.only('start_time', 'end_time', 'trn_dpr_id'):
            s2, e2 = _dpr_interval_minutes(row.start_time, row.end_time)
            if _intervals_overlap(s1, e1, s2, e2):
                self.add_error(
                    'start_time',
                    'This machine already has overlapping production times on this date.',
                )
                break

    def save(self, user=None):
        cd = self.cleaned_data
        working = cd['machine_working'] == DPR_MACHINE_WORKING
        total = dpr_format_total_time(cd['start_time'], cd['end_time'])

        if not working:
            if self._instance and getattr(self._instance, 'pk', None):
                with db_transaction.atomic():
                    row = TrnDpr.objects.select_for_update().get(pk=self._instance.pk)
                    if row.machine_working == DPR_MACHINE_WORKING:
                        reverse_dpr_production_from_inventory(row)
                    row.trn_dpr_dt = cd['trn_dpr_dt']
                    row.section = cd['section']
                    row.machine = cd['machine']
                    row.shift_id = cd['shift']
                    row.machine_working = DPR_MACHINE_NOT_WORKING
                    row.customer = None
                    row.product = None
                    row.batch_line = None
                    row.log_sheet = None
                    row.specification = None
                    row.batch_rem = ''
                    row.lot_no = 0
                    row.qty_kg = Decimal('0')
                    row.qty_nos = 0
                    row.section_qty = None
                    row.batch_size_lakh = None
                    row.start_time = cd['start_time']
                    row.end_time = cd['end_time']
                    row.total_time = total
                    row.operator1 = None
                    row.operator2 = None
                    row.no_of_helper = 0
                    row.remarks = (cd.get('remarks') or '').strip()
                    row.save()
                    row.operators.clear()
                    row.input_batches.all().delete()
                return row

            row = TrnDpr(
                trn_dpr_dt=cd['trn_dpr_dt'],
                section=cd['section'],
                machine=cd['machine'],
                shift_id=cd['shift'],
                machine_working=DPR_MACHINE_NOT_WORKING,
                customer=None,
                product=None,
                batch_line=None,
                log_sheet=None,
                specification=None,
                batch_rem='',
                lot_no=0,
                qty_kg=Decimal('0'),
                qty_nos=0,
                section_qty=None,
                batch_size_lakh=None,
                start_time=cd['start_time'],
                end_time=cd['end_time'],
                total_time=total,
                operator1=None,
                operator2=None,
                no_of_helper=0,
                remarks=(cd.get('remarks') or '').strip(),
            )
            if user and user.is_authenticated:
                row.created_by = user
            row.save()
            row.operators.clear()
            row.input_batches.all().delete()
            return row

        multi_ls_ids = cd.get('_multi_log_sheet_ids')
        spec = cd['_spec']

        if multi_ls_ids is not None:
            if self._instance and getattr(self._instance, 'pk', None):
                try:
                    with db_transaction.atomic():
                        row = TrnDpr.objects.select_for_update().get(pk=self._instance.pk)
                        if row.machine_working == DPR_MACHINE_WORKING:
                            reverse_dpr_production_from_inventory(row)
                        row.trn_dpr_dt = cd['trn_dpr_dt']
                        row.section = cd['section']
                        row.machine = cd['machine']
                        row.shift_id = cd['shift']
                        row.machine_working = DPR_MACHINE_WORKING
                        row.customer = cd['customer']
                        row.product = cd['product']
                        row.batch_line = None
                        row.log_sheet = None
                        row.specification = spec
                        row.batch_rem = (cd.get('batch_rem') or '').strip()[:30]
                        row.lot_no = int(cd['lot_no'])
                        row.qty_kg = cd['qty_kg']
                        row.qty_nos = int(cd['qty_nos'])
                        row.section_qty = cd.get('section_qty')
                        row.batch_size_lakh = cd['batch_size_lakh']
                        row.start_time = cd['start_time']
                        row.end_time = cd['end_time']
                        row.total_time = total
                        row.operator1 = (cd.get('operators') or [None])[0]
                        row.operator2 = (cd.get('operators') or [None, None])[1] if len(cd.get('operators') or []) > 1 else None
                        row.no_of_helper = int(cd.get('no_of_helper') or 0)
                        row.remarks = (cd.get('remarks') or '').strip()[:500]
                        row.save()
                        row.operators.set(cd.get('operators') or [])
                        _sync_dpr_input_batches(row, multi_ls_ids)
                        _mark_logsheets_for_dpr_multi(row)
                        post_dpr_production_to_inventory(row)
                except IntegrityError:
                    raise forms.ValidationError(
                        'Could not save this DPR (constraint violation). Check selections and try again.'
                    ) from None
                return row

            row = TrnDpr(
                trn_dpr_dt=cd['trn_dpr_dt'],
                section=cd['section'],
                machine=cd['machine'],
                shift_id=cd['shift'],
                machine_working=DPR_MACHINE_WORKING,
                customer=cd['customer'],
                product=cd['product'],
                batch_line=None,
                log_sheet=None,
                specification=spec,
                batch_rem=(cd.get('batch_rem') or '').strip()[:30],
                lot_no=int(cd['lot_no']),
                qty_kg=cd['qty_kg'],
                qty_nos=int(cd['qty_nos']),
                section_qty=cd.get('section_qty'),
                batch_size_lakh=cd['batch_size_lakh'],
                start_time=cd['start_time'],
                end_time=cd['end_time'],
                total_time=total,
                operator1=(cd.get('operators') or [None])[0],
                operator2=(cd.get('operators') or [None, None])[1] if len(cd.get('operators') or []) > 1 else None,
                no_of_helper=int(cd.get('no_of_helper') or 0),
                remarks=(cd.get('remarks') or '').strip()[:500],
            )
            if user and user.is_authenticated:
                row.created_by = user
            try:
                with db_transaction.atomic():
                    row.save()
                    row.operators.set(cd.get('operators') or [])
                    _sync_dpr_input_batches(row, multi_ls_ids)
                    _mark_logsheets_for_dpr_multi(row)
                    post_dpr_production_to_inventory(row)
            except IntegrityError:
                raise forms.ValidationError(
                    'Could not save this DPR (constraint violation). Check selections and try again.'
                ) from None
            return row

        line = cd['_batch_line']
        ls = cd['_log_sheet']

        if self._instance and getattr(self._instance, 'pk', None):
            try:
                with db_transaction.atomic():
                    row = TrnDpr.objects.select_for_update().get(pk=self._instance.pk)
                    if row.machine_working == DPR_MACHINE_WORKING:
                        reverse_dpr_production_from_inventory(row)
                    row.trn_dpr_dt = cd['trn_dpr_dt']
                    row.section = cd['section']
                    row.machine = cd['machine']
                    row.shift_id = cd['shift']
                    row.machine_working = DPR_MACHINE_WORKING
                    row.customer = cd['customer']
                    row.product = cd['product']
                    row.batch_line = line
                    row.log_sheet = ls
                    row.specification = spec
                    row.batch_rem = (cd.get('batch_rem') or '').strip()[:30]
                    row.lot_no = int(cd['lot_no'])
                    row.qty_kg = cd['qty_kg']
                    row.qty_nos = int(cd['qty_nos'])
                    row.section_qty = cd.get('section_qty')
                    row.batch_size_lakh = None
                    row.start_time = cd['start_time']
                    row.end_time = cd['end_time']
                    row.total_time = total
                    row.operator1 = (cd.get('operators') or [None])[0]
                    row.operator2 = (cd.get('operators') or [None, None])[1] if len(cd.get('operators') or []) > 1 else None
                    row.no_of_helper = int(cd.get('no_of_helper') or 0)
                    row.remarks = (cd.get('remarks') or '').strip()[:500]
                    row.save()
                    row.operators.set(cd.get('operators') or [])
                    row.input_batches.all().delete()
                    post_dpr_production_to_inventory(row)
            except IntegrityError:
                raise forms.ValidationError(
                    'Duplicate DPR: this batch, log sheet, machine, shift, section, and date combination already exists.'
                ) from None
            return row

        row = TrnDpr(
            trn_dpr_dt=cd['trn_dpr_dt'],
            section=cd['section'],
            machine=cd['machine'],
            shift_id=cd['shift'],
            machine_working=DPR_MACHINE_WORKING,
            customer=cd['customer'],
            product=cd['product'],
            batch_line=line,
            log_sheet=ls,
            specification=spec,
            batch_rem=(cd.get('batch_rem') or '').strip()[:30],
            lot_no=int(cd['lot_no']),
            qty_kg=cd['qty_kg'],
            qty_nos=int(cd['qty_nos']),
            section_qty=cd.get('section_qty'),
            batch_size_lakh=None,
            start_time=cd['start_time'],
            end_time=cd['end_time'],
            total_time=total,
            operator1=(cd.get('operators') or [None])[0],
            operator2=(cd.get('operators') or [None, None])[1] if len(cd.get('operators') or []) > 1 else None,
            no_of_helper=int(cd.get('no_of_helper') or 0),
            remarks=(cd.get('remarks') or '').strip()[:500],
        )
        if user and user.is_authenticated:
            row.created_by = user
        try:
            with db_transaction.atomic():
                row.save()
                row.operators.set(cd.get('operators') or [])
                row.input_batches.all().delete()
                post_dpr_production_to_inventory(row)
        except IntegrityError:
            raise forms.ValidationError(
                'Duplicate DPR: this batch, log sheet, machine, shift, section, and date combination already exists.'
            ) from None
        return row
