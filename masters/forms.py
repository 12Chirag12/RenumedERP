"""
masters/forms.py

Every form implements the two-method contract required by combined_view():

    get_initial(self) -> dict
        Returns field-name → value for pre-filling on GET in edit mode.
        Returns {} when self.instance is None.

    save(self) -> model instance
        Called after form.is_valid().  Creates or updates depending on
        whether self.instance is set.  Catches IntegrityError (M3) so
        that a concurrent duplicate submission produces a clean form
        error instead of a 500.
"""
import os
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django import forms
from django.db import IntegrityError
import json as _json
import re   as _re
from django.db import transaction as db_transaction

from .models import (
    MstDepartment, MstSection, MstMachine, MstOperator, MstOperatorSection, MstUom, MstState,
    MstTransport, MstPdnStage, MstItemType,
    MstColor, MstShape, MstCoatType, MstProdCat, MstCapsule,
    MstPkgStyle, MstExpenses, MstExpGroup, MstProd, MstItem, MstCust, MstSupplier, MstCustProd,
    MstBomRmHed, MstBomRmDtl, MstBomPmHed, MstBomPmDtl
)
from django.utils import timezone


def _bom_batch_nos_from_lakh(batch_size):
    """Integer count from batch size expressed in lakh: nos = lakh × 100,000."""
    d = Decimal(str(batch_size))
    return int((d * Decimal('100000')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _bom_products_for_customer(customer_id):
    if not customer_id:
        return MstProd.objects.none()
    return (
        MstProd.objects.filter(cust_products__customer_id=customer_id)
        .select_related('prod_type')
        .order_by('prod_name')
        .distinct()
    )


# ═══════════════════════════════════════════════════════════════
#  SECTION FORM
# ═══════════════════════════════════════════════════════════════

class SectionForm(forms.Form):
    """
    Used for both create and edit.
    On edit, pass instance=<MstSection obj> so uniqueness checks
    correctly exclude the current record.
    """

    section_name = forms.CharField(
        max_length=150,
        label='Section Name',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Enter section name',
            'id':           'sectionNameInput',
            'autocomplete': 'off',
        })
    )

    # M2: queryset set to none() at class level; populated fresh per-request
    # in __init__ so long-running production workers always show current data.
    department = forms.ModelChoiceField(
        queryset=MstDepartment.objects.none(),
        label='Department',
        empty_label='— Select Department —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown',
            'id':    'deptDropdown',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        # M2: assign live queryset per-request, not at class-import time.
        self.fields['department'].queryset = MstDepartment.objects.all()

    def clean_section_name(self):
        name = self.cleaned_data.get('section_name', '').strip()
        qs = MstSection.objects.filter(section_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                f'A section named "{name}" already exists.'
            )
        return name

    def clean(self):
        cleaned_data = super().clean()
        section_name = cleaned_data.get('section_name', '').strip()
        department   = cleaned_data.get('department')

        if section_name and department:
            qs = MstSection.objects.filter(
                section_name__iexact=section_name,
                department=department
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'Section "{section_name}" already exists under "{department.dept_name}".'
                )

        return cleaned_data

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'section_name': self.instance.section_name,
            'department':   self.instance.department,
        }

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.section_name = cd['section_name']
                self.instance.department   = cd['department']
                self.instance.save()
                return self.instance
            return MstSection.objects.create(
                section_name=cd['section_name'],
                department=cd['department'],
            )
        except IntegrityError:
            # M3: concurrent duplicate submission — surface as a form error.
            raise forms.ValidationError(
                f'A section named "{cd["section_name"]}" already exists '
                '(saved by another user just now). Please choose a different name.'
            )


# ═══════════════════════════════════════════════════════════════
#  MACHINE FORM
# ═══════════════════════════════════════════════════════════════

class MachineForm(forms.Form):
    """
    Used for both create and edit of MstMachine records.
    Pass instance=<MstMachine obj> on edit to exclude self from uniqueness check.
    """

    machine_name = forms.CharField(
        max_length=200,
        label='Machine Name',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Enter machine name',
            'id':           'machineNameInput',
            'autocomplete': 'off',
        })
    )

    # M2: queryset set to none() at class level; populated per-request in __init__.
    section = forms.ModelChoiceField(
        queryset=MstSection.objects.none(),
        label='Section',
        empty_label='— Select Section —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown',
            'id':    'sectionDropdown',
        })
    )

    make = forms.CharField(
        max_length=150,
        required=False,
        label='Make',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Enter make',
            'autocomplete': 'off',
        })
    )

    model_no = forms.CharField(
        max_length=100,
        required=False,
        label='Model No.',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Model no.',
            'autocomplete': 'off',
        })
    )

    machine_no = forms.CharField(
        max_length=100,
        required=False,
        label='Machine No.',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Machine number / asset tag',
            'autocomplete': 'off',
        })
    )

    capacity = forms.CharField(
        max_length=100,
        required=False,
        label='Capacity',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Capacity',
            'autocomplete': 'off',
        })
    )

    installed_date = forms.DateField(
        required=False,
        label='Installation Date',
        widget=forms.DateInput(attrs={
            'class': 'cu-input',
            'type':  'date',
            'id':    'installedDateInput',
        })
    )

    remarks = forms.CharField(
        required=False,
        label='Remarks',
        widget=forms.Textarea(attrs={
            'class':       'cu-textarea',
            'placeholder': 'Optional remarks…',
            'rows':        3,
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        # M2: live queryset per-request.
        self.fields['section'].queryset = MstSection.objects.select_related('department').all()

    def clean_machine_name(self):
        name = self.cleaned_data.get('machine_name', '').strip()
        qs = MstMachine.objects.filter(machine_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                f'A machine named "{name}" already exists.'
            )
        return name

    def clean_installed_date(self):
        date = self.cleaned_data.get('installed_date')
        if date and date > timezone.now().date():
            raise forms.ValidationError('Installation date cannot be a future date.')
        return date

    def get_initial(self):
        if not self.instance:
            return {}
        inst = self.instance
        return {
            'machine_name':   inst.machine_name,
            'section':        inst.section,
            'make':           inst.make,
            'model_no':       inst.model_no,
            'machine_no':     inst.machine_no,
            'capacity':       inst.capacity,
            'installed_date': inst.installed_date,
            'remarks':        inst.remarks,
        }

    def save(self):
        """
        Optional text fields map to nullable DB columns — coerced to None
        so blank submissions never write empty strings to the DB.
        """
        cd = self.cleaned_data
        fields = dict(
            machine_name=cd['machine_name'],
            section=cd['section'],
            make=cd.get('make') or None,
            model_no=cd.get('model_no') or None,
            machine_no=cd.get('machine_no') or None,
            capacity=cd.get('capacity') or None,
            installed_date=cd.get('installed_date') or None,
            remarks=cd.get('remarks') or None,
        )
        try:
            if self.instance:
                for attr, val in fields.items():
                    setattr(self.instance, attr, val)
                self.instance.save()
                return self.instance
            return MstMachine.objects.create(**fields)
        except IntegrityError:
            raise forms.ValidationError(
                f'A machine named "{cd["machine_name"]}" already exists '
                '(saved by another user just now).'
            )


# ═══════════════════════════════════════════════════════════════
#  OPERATOR FORM
# ═══════════════════════════════════════════════════════════════

class OperatorForm(forms.Form):
    """Create / edit MstOperator with one or more sections."""

    opt_name = forms.CharField(
        max_length=30,
        label='Operator name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input',
            'placeholder': 'Enter operator name',
            'id': 'operatorNameInput',
            'autocomplete': 'off',
        }),
    )
    designation = forms.CharField(
        max_length=200,
        required=False,
        label='Designation',
        widget=forms.TextInput(attrs={
            'class': 'cu-input',
            'placeholder': 'e.g. Sr. Operator',
            'id': 'operatorDesignationInput',
            'autocomplete': 'off',
        }),
    )
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.operator_section_list = list(
            MstSection.objects.select_related('department').order_by(
                'department__dept_name', 'section_name'
            )
        )

    def clean_opt_name(self):
        name = self.cleaned_data.get('opt_name', '').strip()
        qs = MstOperator.objects.filter(opt_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'An operator named "{name}" already exists.')
        return name

    @property
    def selected_section_id_set(self):
        """PK set for template checkboxes (POST survives validation errors)."""
        if self.is_bound:
            out = set()
            for x in self.data.getlist('sections'):
                try:
                    out.add(int(x))
                except (TypeError, ValueError):
                    pass
            return out
        init = (self.initial or {}).get('sections') or []
        if not isinstance(init, (list, tuple)):
            return set()
        out = set()
        for x in init:
            try:
                out.add(int(x))
            except (TypeError, ValueError):
                pass
        return out

    def clean(self):
        cleaned = super().clean()
        allowed = {s.section_id for s in self.operator_section_list}
        raw = self.data.getlist('sections')
        ids = []
        for x in raw:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                self.add_error(None, 'Invalid section selection.')
                return cleaned
        uniq = list(dict.fromkeys(ids))
        if not uniq:
            self.add_error(None, 'Select at least one section.')
            return cleaned
        if not set(uniq).issubset(allowed):
            self.add_error(None, 'Invalid section selection.')
            return cleaned
        cleaned['sections'] = list(MstSection.objects.filter(pk__in=uniq))
        return cleaned

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'opt_name': self.instance.opt_name,
            'designation': self.instance.designation or '',
            'sections': [
                str(i)
                for i in self.instance.section_links.values_list('section_id', flat=True)
            ],
        }

    def save(self):
        cd = self.cleaned_data
        des = (cd.get('designation') or '').strip() or None
        try:
            with db_transaction.atomic():
                if self.instance:
                    self.instance.opt_name = cd['opt_name']
                    self.instance.designation = des
                    self.instance.save()
                    op = self.instance
                else:
                    op = MstOperator.objects.create(opt_name=cd['opt_name'], designation=des)
                op.section_links.all().delete()
                MstOperatorSection.objects.bulk_create(
                    [MstOperatorSection(operator=op, section=s) for s in cd['sections']]
                )
                return op
        except IntegrityError:
            raise forms.ValidationError(
                f'Operator "{cd["opt_name"]}" already exists (saved by another user just now).'
            )


# ═══════════════════════════════════════════════════════════════
#  UOM FORM
# ═══════════════════════════════════════════════════════════════

class UomForm(forms.Form):
    """
    Create / edit a Unit of Measurement record.
    Pass instance=<MstUom obj> on edit.
    """
    uom_name = forms.CharField(
        max_length=150,
        label='Unit of Measurement',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Enter unit name',
            'id':           'uomNameInput',
            'autocomplete': 'off',
        })
    )

    short_name = forms.CharField(
        max_length=3,
        label='Abbreviation',
        widget=forms.TextInput(attrs={
            'class':        'cu-input abbr-input',
            'placeholder':  'e.g. Bgs',
            'id':           'shortNameInput',
            'autocomplete': 'off',
            'maxlength':    '3',
            'disabled':     'disabled',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['short_name'].widget.attrs.pop('disabled', None)

    def clean_uom_name(self):
        name = self.cleaned_data.get('uom_name', '').strip()
        qs = MstUom.objects.filter(uom_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'UOM "{name}" already exists.')
        return name

    def clean_short_name(self):
        sn = self.cleaned_data.get('short_name', '').strip()
        if len(sn) > 3:
            raise forms.ValidationError('Abbreviation must be 3 characters or fewer.')
        qs = MstUom.objects.filter(short_name__iexact=sn)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Abbreviation "{sn}" already exists.')
        return sn

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'uom_name':   self.instance.uom_name,
            'short_name': self.instance.short_name,
        }

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.uom_name   = cd['uom_name']
                self.instance.short_name = cd['short_name']
                self.instance.save()
                return self.instance
            return MstUom.objects.create(
                uom_name=cd['uom_name'],
                short_name=cd['short_name'],
            )
        except IntegrityError:
            raise forms.ValidationError(
                f'UOM "{cd["uom_name"]}" or abbreviation "{cd["short_name"]}" '
                'already exists (saved by another user just now).'
            )


# ═══════════════════════════════════════════════════════════════
#  PRODUCT ATTRIBUTE FORMS
# ═══════════════════════════════════════════════════════════════
from .models import MstColor, MstShape, MstCoatType, MstProdCat, MstCapsule

# Field name in DB for each simple type
_ATTR_DB_FIELD = {
    MstColor:    'color_name',
    MstShape:    'shape_name',
    MstCoatType: 'coating_name',
}


class SimpleAttrForm(forms.Form):
    """
    Shared base for single-field attribute forms (colour, shape, coating).

    get_initial / save use _ATTR_DB_FIELD to resolve the correct model
    field for each subclass, so ColorForm / ShapeForm / CoatTypeForm need
    no further overrides.
    """
    model      = None
    label_text = 'Name'

    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'id': 'attrNameInput', 'autocomplete': 'off',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['name'].label = self.label_text
        self.fields['name'].widget.attrs['placeholder'] = f'Enter {self.label_text.lower()}'

    def clean_name(self):
        value    = self.cleaned_data.get('name', '').strip()
        db_field = _ATTR_DB_FIELD[self.model]
        qs = self.model.objects.filter(**{db_field + '__iexact': value})
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'{value} already exists.')
        return value

    def get_initial(self):
        if not self.instance:
            return {}
        db_field = _ATTR_DB_FIELD[self.model]
        return {'name': getattr(self.instance, db_field)}

    def save(self):
        db_field = _ATTR_DB_FIELD[self.model]
        value    = self.cleaned_data['name']
        try:
            if self.instance:
                setattr(self.instance, db_field, value)
                self.instance.save()
                return self.instance
            return self.model.objects.create(**{db_field: value})
        except IntegrityError:
            raise forms.ValidationError(
                f'"{value}" already exists (saved by another user just now).'
            )


class ColorForm(SimpleAttrForm):
    model      = MstColor
    label_text = 'Colour Name'


class ShapeForm(SimpleAttrForm):
    model      = MstShape
    label_text = 'Shape Name'


class CoatTypeForm(SimpleAttrForm):
    model      = MstCoatType
    label_text = 'Coating Type'


# ── ProdCatForm ───────────────────────────────────────────────────────────────

class ProdCatForm(forms.Form):
    prod_cat_id = forms.CharField(
        max_length=2, label='Category ID (2 chars)',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'placeholder': 'e.g. TB',
                                      'id': 'prodCatIdInput', 'autocomplete': 'off', 'maxlength': '2'})
    )
    prod_cat_name = forms.CharField(
        max_length=150, label='Category Name',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'placeholder': 'Enter category name',
                                      'id': 'attrNameInput', 'autocomplete': 'off'})
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

    def clean_prod_cat_id(self):
        code = self.cleaned_data.get('prod_cat_id', '').strip().upper()
        if len(code) != 2:
            raise forms.ValidationError('Category ID must be exactly 2 characters.')
        if not code.isalpha():
            raise forms.ValidationError("Category ID must contain only letters.")
        qs = MstProdCat.objects.filter(prod_cat_id__iexact=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Category ID "{code}" already exists.')
        return code

    def clean_prod_cat_name(self):
        name = self.cleaned_data.get('prod_cat_name', '').strip()
        qs = MstProdCat.objects.filter(prod_cat_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Category "{name}" already exists.')
        return name

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'prod_cat_id':   self.instance.prod_cat_id,
            'prod_cat_name': self.instance.prod_cat_name,
        }

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.prod_cat_id   = cd['prod_cat_id']
                self.instance.prod_cat_name = cd['prod_cat_name']
                self.instance.save()
                return self.instance
            return MstProdCat.objects.create(
                prod_cat_id=cd['prod_cat_id'],
                prod_cat_name=cd['prod_cat_name'],
            )
        except IntegrityError:
            raise forms.ValidationError(
                f'Category ID "{cd["prod_cat_id"]}" or name "{cd["prod_cat_name"]}" '
                'already exists (saved by another user just now).'
            )


# ── CapsuleForm ───────────────────────────────────────────────────────────────

class CapsuleForm(forms.Form):
    capsule_size = forms.CharField(
        max_length=100, label='Capsule Size',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'placeholder': 'e.g. Size 0',
                                      'id': 'capsuleSizeInput', 'autocomplete': 'off'})
    )
    capsule_color = forms.CharField(
        max_length=100, label='Capsule Colour',
        widget=forms.TextInput(attrs={'class': 'cu-input', 'placeholder': 'e.g. Clear',
                                      'id': 'capsuleColorInput', 'autocomplete': 'off'})
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

    def clean_capsule_size(self):
        return self.cleaned_data.get('capsule_size', '').strip()

    def clean_capsule_color(self):
        return self.cleaned_data.get('capsule_color', '').strip()

    def clean(self):
        cleaned = super().clean()
        size  = cleaned.get('capsule_size')
        color = cleaned.get('capsule_color')

        if size and color:
            qs = MstCapsule.objects.filter(
                capsule_size__iexact=size,
                capsule_color__iexact=color,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'capsule_color',
                    f'Capsule "{size} {color}" already exists.',
                )
        return cleaned

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'capsule_size':  self.instance.capsule_size,
            'capsule_color': self.instance.capsule_color,
        }

    def save(self):
        """
        capsule_name is derived from size + color.  The model's own save()
        override (L2 fix) recomputes it automatically, so we simply pass
        size and color and let the model handle the rest.
        """
        cd    = self.cleaned_data
        size  = cd['capsule_size']
        color = cd['capsule_color']
        try:
            if self.instance:
                self.instance.capsule_size  = size
                self.instance.capsule_color = color
                self.instance.save()          # model.save() recomputes capsule_name
                return self.instance
            return MstCapsule.objects.create(capsule_size=size, capsule_color=color)
        except IntegrityError:
            self.add_error(
                'capsule_color',
                f'Capsule "{size} {color}" already exists '
                '(saved by another user just now).',
            )
            raise forms.ValidationError('')


# ═══════════════════════════════════════════════════════════════
#  LOGISTICS FORMS (Transporter + State)
# ═══════════════════════════════════════════════════════════════

class StateForm(forms.Form):
    """
    Create / edit a State record.
    Pass instance=<MstState obj> on edit.
    """
    state_name = forms.CharField(
        max_length=150,
        label='State Name',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'Enter state name',
            'id':           'stateNameInput',
            'autocomplete': 'off',
        })
    )

    gst_code = forms.CharField(
        max_length=2,
        label='GST Code',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'e.g. 27',
            'id':           'gstCodeInput',
            'autocomplete': 'off',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

    def clean_state_name(self):
        name = self.cleaned_data.get('state_name', '').strip()
        qs = MstState.objects.filter(state_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'State "{name}" already exists.')
        return name

    def clean_gst_code(self):
        code = self.cleaned_data.get('gst_code', '').strip()
        qs = MstState.objects.filter(gst_code__iexact=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if code.isdigit():
            code = code.zfill(2)
        else:
            raise forms.ValidationError("GST Code must contain only numbers.")
        if qs.exists():
            raise forms.ValidationError(f'GST Code "{code}" already exists.')
        return code

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'state_name': self.instance.state_name,
            'gst_code':   self.instance.gst_code,
        }

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.state_name = cd['state_name']
                self.instance.gst_code   = cd['gst_code']
                self.instance.save()
                return self.instance
            return MstState.objects.create(
                state_name=cd['state_name'],
                gst_code=cd['gst_code'],
            )
        except IntegrityError:
            raise forms.ValidationError(
                f'State "{cd["state_name"]}" or GST Code "{cd["gst_code"]}" '
                'already exists (saved by another user just now).'
            )


class TransporterForm(forms.Form):
    transport_name = forms.CharField(
        max_length=150, label='Transporter Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Enter transporter name',
            'id': 'transporterNameInput', 'autocomplete': 'off',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

    def clean_transport_name(self):
        name = self.cleaned_data.get('transport_name', '').strip()
        qs = MstTransport.objects.filter(transport_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Transporter "{name}" already exists.')
        return name

    def get_initial(self):
        if not self.instance:
            return {}
        return {'transport_name': self.instance.transport_name}

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.transport_name = cd['transport_name']
                self.instance.save()
                return self.instance
            return MstTransport.objects.create(transport_name=cd['transport_name'])
        except IntegrityError:
            raise forms.ValidationError(
                f'Transporter "{cd["transport_name"]}" already exists '
                '(saved by another user just now).'
            )


# ═══════════════════════════════════════════════════════════════
#  PRODUCTION STAGE FORM
# ═══════════════════════════════════════════════════════════════

class ProdStageForm(forms.Form):
    stage_name = forms.CharField(
        max_length=150, label='Production Stage Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Enter stage name',
            'id': 'stageNameInput', 'autocomplete': 'off',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

    def clean_stage_name(self):
        name = self.cleaned_data.get('stage_name', '').strip()
        qs = MstPdnStage.objects.filter(stage_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Stage "{name}" already exists.')
        return name

    def get_initial(self):
        if not self.instance:
            return {}
        return {'stage_name': self.instance.stage_name}

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.stage_name = cd['stage_name']
                self.instance.save()
                return self.instance
            return MstPdnStage.objects.create(stage_name=cd['stage_name'])
        except IntegrityError:
            raise forms.ValidationError(
                f'Stage "{cd["stage_name"]}" already exists '
                '(saved by another user just now).'
            )


# ═══════════════════════════════════════════════════════════════
#  ITEM TYPE FORM
# ═══════════════════════════════════════════════════════════════

class ItemTypeForm(forms.Form):
    # M2: queryset set to none() at class level; populated per-request in __init__.
    item_category = forms.ModelChoiceField(
        queryset=MstProdCat.objects.none(),
        label='Item Category',
        empty_label='— Select Category —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'itemCategorySelect'})
    )
    item_type_name = forms.CharField(
        max_length=150, label='Item Type Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Enter item type name',
            'id': 'itemTypeNameInput', 'autocomplete': 'off',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        # M2: live queryset per-request.
        self.fields['item_category'].queryset = MstProdCat.objects.all()

    def clean_item_type_name(self):
        name = self.cleaned_data.get('item_type_name', '').strip()
        qs = MstItemType.objects.filter(item_type_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Item type "{name}" already exists.')
        return name

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'item_category':  self.instance.item_category,
            'item_type_name': self.instance.item_type_name,
        }

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.item_category  = cd['item_category']
                self.instance.item_type_name = cd['item_type_name']
                self.instance.save()
                return self.instance
            return MstItemType.objects.create(
                item_category=cd['item_category'],
                item_type_name=cd['item_type_name'],
            )
        except IntegrityError:
            raise forms.ValidationError(
                f'Item type "{cd["item_type_name"]}" already exists '
                '(saved by another user just now).'
            )


# ═══════════════════════════════════════════════════════════════
#  PACKING STYLE FORM
# ═══════════════════════════════════════════════════════════════

class PkgStyleForm(forms.Form):
    """
    Create / edit a Packing Style record.
    Validation:
      - pkg_style_name: digits and uppercase X only (e.g. 100X10).
      - (pkg_style_name + pkg_type) must be unique.
      - pkg_style_value must be > 0.
    Pass instance=<MstPkgStyle obj> on edit to exclude self from uniqueness check.
    """

    pkg_style_name = forms.CharField(
        max_length=150,
        label='Packing Style Name',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'e.g. 100X10',
            'id':           'pkgStyleNameInput',
            'autocomplete': 'off',
        })
    )

    pkg_style_value = forms.IntegerField(
        min_value=1,
        label='Packing Style Value',
        widget=forms.NumberInput(attrs={
            'class':        'cu-input',
            'placeholder':  'e.g. 1000',
            'id':           'pkgStyleValueInput',
            'min':          '1',
        })
    )

    # M2: queryset set to none() at class level; populated per-request in __init__.
    pkg_type = forms.ModelChoiceField(
        queryset=MstItemType.objects.none(),
        label='Packing Type (Item Type)',
        empty_label='— Select Item Type —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown',
            'id':    'pkgItemTypeSelect',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        # M2: live queryset per-request.
        self.fields['pkg_type'].queryset = MstItemType.objects.all()

    def clean_pkg_style_name(self):
        val = self.cleaned_data.get('pkg_style_name', '').strip().upper()
        if not val:
            raise forms.ValidationError('This field is required.')
        if not _re.fullmatch(r'[0-9X]+', val):
            raise forms.ValidationError('Use only digits and X (e.g. 100X10).')
        return val

    def clean(self):
        cleaned  = super().clean()
        name     = (cleaned.get('pkg_style_name') or '').strip()
        pkg_type = cleaned.get('pkg_type')

        if name and pkg_type:
            qs = MstPkgStyle.objects.filter(
                pkg_style_name__iexact=name,
                pkg_type=pkg_type,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'pkg_style_name',
                    f'Packing Style "{name}" already exists for item type '
                    f'"{pkg_type.item_type_name}".',
                )
        return cleaned

    def clean_pkg_style_value(self):
        value = self.cleaned_data.get('pkg_style_value')
        if value is not None and value < 1:
            raise forms.ValidationError('Value must be greater than zero.')
        return value

    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'pkg_style_name':  self.instance.pkg_style_name,
            'pkg_style_value': self.instance.pkg_style_value,
            'pkg_type':        self.instance.pkg_type,
        }

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.pkg_style_name  = cd['pkg_style_name']
                self.instance.pkg_style_value = cd['pkg_style_value']
                self.instance.pkg_type        = cd['pkg_type']
                self.instance.save()
                return self.instance
            return MstPkgStyle.objects.create(
                pkg_style_name=cd['pkg_style_name'],
                pkg_style_value=cd['pkg_style_value'],
                pkg_type=cd['pkg_type'],
            )
        except IntegrityError:
            self.add_error(
                'pkg_style_name',
                f'Packing Style "{cd["pkg_style_name"]}" already exists for this '
                'item type (saved by another user just now).',
            )
            raise forms.ValidationError('')


# ═══════════════════════════════════════════════════════════════
#  EXPENSES FORM
# ═══════════════════════════════════════════════════════════════

class ExpensesForm(forms.Form):
    """
    Create / edit an Expense record.
    Validation:
      - exp_name must be unique (case-insensitive).
    Pass instance=<MstExpenses obj> on edit.
    """

    exp_name = forms.CharField(
        max_length=200,
        label='Expense Name',
        widget=forms.TextInput(attrs={
            'class':        'cu-input',
            'placeholder':  'e.g. Operator Salary',
            'id':           'expNameInput',
            'autocomplete': 'off',
        })
    )
    expgroup= forms.ModelChoiceField(
        queryset=MstExpGroup.objects.none(),
        label='Expenses Group',
        empty_label='— Select Group Type —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown', 'id': 'expGroupSelect',
        })
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['expgroup'].queryset = MstExpGroup.objects.all().order_by('exp_group')

    def clean_exp_name(self):
        name = self.cleaned_data.get('exp_name', '').strip()
        qs = MstExpenses.objects.filter(exp_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Expense "{name}" already exists.')
        return name


    def get_initial(self):
        if not self.instance:
            return {}
        return {
            'exp_name': self.instance.exp_name,
            'expgroup': self.instance.exp_group,
            }

    def save(self):
        cd = self.cleaned_data
        try:
            if self.instance:
                self.instance.exp_name = cd['exp_name']
                self.instance.exp_group = cd['expgroup']
                self.instance.save()
                return self.instance
            return MstExpenses.objects.create(
                exp_name=cd['exp_name'],
                exp_group=cd['expgroup'],
            )
        except IntegrityError:
            raise forms.ValidationError(
                f'Expense "{cd["exp_name"]}" already exists '
                '(saved by another user just now).'
            )
        
class ProductForm(forms.Form):
    """
    Create / edit a Product (MstProd) record.
    Pass instance=<MstProd obj> on edit.
 
    FK handling:
    - prod_type       : ModelChoiceField — Django submits & resolves item_type_id
                        automatically. Saved as prod_type_id (int) in MstProd.
    - prod_category   : NOT a ModelChoiceField — category is read-only, auto-filled
                        by JS from the selected prod_type's item_category FK.
                        The hidden field prod_category_id carries the raw PK value
                        (a 2-char string like "TB"). clean_prod_category_id()
                        resolves it to a MstProdCat instance which save() assigns.
    """
 
    prod_name = forms.CharField(
        max_length=200,
        label='Product Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Enter product name',
            'id': 'prodNameInput', 'autocomplete': 'off',
        }),
    )
 
    generic_name = forms.CharField(
        label='Generic Name',
        widget=forms.Textarea(attrs={
            'class': 'cu-textarea', 'placeholder': 'Enter generic / chemical name…',
            'id': 'genericNameInput', 'rows': 3,
        }),
    )
 
    # M2: queryset populated per-request in __init__
    prod_type = forms.ModelChoiceField(
        queryset=MstItemType.objects.none(),
        label='Product Type',
        empty_label='— Select Product Type —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown', 'id': 'prodTypeSelect',
        }),
    )
 
    # Hidden field — carries the raw prod_cat_id string PK (e.g. "TB")
    # set by JS when prod_type changes.
    # CharField (not IntegerField) because MstProdCat.prod_cat_id is
    # CharField(max_length=2), NOT an integer.
    prod_category_id = forms.CharField(
        max_length=2,
        widget=forms.HiddenInput(attrs={'id': 'prodCategoryIdHidden'}),
        required=True,
    )
 
    hsn_code = forms.CharField(
        max_length=50, required=False, label='HSN Code',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'e.g. 30049099',
            'id': 'hsnCodeInput', 'autocomplete': 'off',
        }),
    )
 
    # M2: queryset populated per-request in __init__
    uom = forms.ModelChoiceField(
        queryset=MstUom.objects.none(),
        label='UOM',
        empty_label='— Select UOM —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown', 'id': 'uomSelect',
        }),
    )
 
    tablet_layer = forms.ChoiceField(
        choices=[('Single', 'Single'), ('Double', 'Double')],
        label='Tablet Layers',
        initial='Single',
        widget=forms.RadioSelect(attrs={'class': 'layer-radio'}),
    )
 
    first_color = forms.ModelChoiceField(
        queryset=MstColor.objects.none(),
        label='First Color', required=False,
        empty_label='— Select Colour —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown', 'id': 'firstColorSelect', 'disabled': 'disabled',
        }),
    )
 
    second_color = forms.ModelChoiceField(
        queryset=MstColor.objects.none(),
        label='Second Color', required=False,
        empty_label='— Select Colour —',
        widget=forms.Select(attrs={
            'class': 'cu-select searchable-dropdown', 'id': 'secondColorSelect', 'disabled': 'disabled',
        }),
    )
 
    product_image = forms.ImageField(
        required=False, label='Product Image',
        widget=forms.FileInput(attrs={
            'class': 'prod-image-input', 'id': 'productImageInput', 'accept': 'image/*',
        }),
    )
 
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        # M2: live querysets per-request
        self.fields['prod_type'].queryset = (
            MstItemType.objects.select_related('item_category')
            .filter(item_category__prod_cat_name__iexact='Finished Goods')
        )
        self.fields['uom'].queryset           = MstUom.objects.all()
        self.fields['first_color'].queryset   = MstColor.objects.all()
        self.fields['second_color'].queryset  = MstColor.objects.all()
 
        # On edit, re-enable colour selects when layer is Double
        if self.instance and self.instance.tablet_layer == 'Double':
            self.fields['first_color'].widget.attrs.pop('disabled', None)
            self.fields['second_color'].widget.attrs.pop('disabled', None)
 
    # ── Field-level validation ──────────────────────────────────
 
    def clean_prod_name(self):
        name = self.cleaned_data.get('prod_name', '').strip()
        qs = MstProd.objects.filter(prod_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Product "{name}" already exists.')
        return name
 
    def clean_generic_name(self):
        value = self.cleaned_data.get('generic_name', '').strip()
        if not value:
            raise forms.ValidationError('Generic name must not be blank.')
        return value
 
    def clean_prod_category_id(self):
        """
        prod_category_id is the raw 2-char string PK from MstProdCat
        (e.g. "TB"). Resolve it to a MstProdCat instance so save()
        can assign the FK directly without a second lookup.
        Stored back into cleaned_data as the MstProdCat object.
        """
        raw = self.cleaned_data.get('prod_category_id', '').strip().upper()
        if not raw:
            raise forms.ValidationError('Product category is required.')
        try:
            return MstProdCat.objects.get(pk=raw)
        except MstProdCat.DoesNotExist:
            raise forms.ValidationError(
                f'Product category "{raw}" does not exist.'
            )
 
    def clean_hsn_code(self):
        return self.cleaned_data.get('hsn_code', '').strip() or None
 
    # ── Cross-field validation ──────────────────────────────────
 
    def clean(self):
        cleaned      = super().clean()
        layer        = cleaned.get('tablet_layer')
        first_color  = cleaned.get('first_color')
        second_color = cleaned.get('second_color')
 
        if layer == 'Double':
            if not first_color:
                self.add_error('first_color', 'First colour is required for double-layer tablets.')
            if not second_color:
                self.add_error('second_color', 'Second colour is required for double-layer tablets.')
            if first_color and second_color and first_color == second_color:
                self.add_error('second_color', 'First and second colours must be different.')
        else:
            # Single layer → clear colour selections
            cleaned['first_color']  = None
            cleaned['second_color'] = None
 
        return cleaned
 
    # ── Form contract ───────────────────────────────────────────
 
    def get_initial(self):
        if not self.instance:
            return {}
        inst = self.instance
        return {
            'prod_name':         inst.prod_name,
            'generic_name':      inst.generic_name,
            'prod_type':         inst.prod_type,
            # prod_category_id hidden field needs the raw PK string
            'prod_category_id':  inst.prod_category_id,
            'uom':               inst.uom,
            'hsn_code':          inst.hsn_code,
            'tablet_layer':      inst.tablet_layer,
            'first_color':       inst.first_color,
            'second_color':      inst.second_color,
        }
 
    def save(self, image_file=None):
        """
        FK assignments:
          prod_type     = cd['prod_type']         → MstItemType instance
                          (resolved by ModelChoiceField; Django writes item_type_id)
          prod_category = cd['prod_category_id']  → MstProdCat instance
                          (resolved in clean_prod_category_id; Django writes prod_cat_id)
 
        image_file: optional InMemoryUploadedFile from request.FILES.
                    Written to MEDIA_ROOT/products/; relative path stored in image_path.
                    Existing path is kept when no new file is supplied.
        """
        cd = self.cleaned_data
 
        image_path = self.instance.image_path if self.instance else None
        if image_file:
            if self.instance and self.instance.image_path:
                old_full = os.path.join(settings.MEDIA_ROOT, self.instance.image_path)
                if os.path.isfile(old_full):
                    os.remove(old_full)
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'products')
            os.makedirs(upload_dir, exist_ok=True)
            ext = os.path.splitext(getattr(image_file, 'name', '') or '')[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                ext = '.jpg'
            stem_a = _re.sub(r'[^\w\s\-]', '', str(cd['prod_name']))
            stem_a = _re.sub(r'\s+', '_', stem_a).strip('_')[:120] or 'product'
            stem_b = _re.sub(r'[^\w\s\-]', '', str(cd['prod_type'].item_type_name))
            stem_b = _re.sub(r'\s+', '_', stem_b).strip('_')[:120] or 'type'
            safe_name = f'{stem_a}-{stem_b}{ext}'
            dest_rel = f'products/{safe_name}'
            dest_path = os.path.join(settings.MEDIA_ROOT, dest_rel)
            with open(dest_path, 'wb+') as fh:
                for chunk in image_file.chunks():
                    fh.write(chunk)
            image_path = dest_rel
 
        fields = dict(
            prod_name     = cd['prod_name'],
            generic_name  = cd['generic_name'],
            prod_type     = cd['prod_type'],         # MstItemType instance → saves item_type_id
            prod_category = cd['prod_category_id'],  # MstProdCat instance  → saves prod_cat_id
            uom           = cd['uom'],
            hsn_code      = cd.get('hsn_code') or None,
            tablet_layer  = cd['tablet_layer'],
            first_color   = cd.get('first_color') or None,
            second_color  = cd.get('second_color') or None,
            image_path    = image_path,
        )
 
        try:
            if self.instance:
                for attr, val in fields.items():
                    setattr(self.instance, attr, val)
                self.instance.save()
                return self.instance
            return MstProd.objects.create(**fields)
        except IntegrityError:
            raise forms.ValidationError(
                f'Product "{cd["prod_name"]}" already exists '
                '(saved by another user just now).'
            )
        
class ItemForm(forms.Form):
    """
    Create / edit an Item (MstItem) record.
    Pass instance=<MstItem obj> on edit.
    """
 
    YN_CHOICES = [('Y', 'Yes'), ('N', 'No')]
 
    item_name = forms.CharField(
        max_length=200, label='Item Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Enter item name',
            'id': 'itemNameInput', 'autocomplete': 'off',
        }),
    )
 
    # M2: queryset populated per-request in __init__
    item_type = forms.ModelChoiceField(
        queryset=MstItemType.objects.none(),
        label='Item Type', empty_label='— Select Item Type —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'itemTypeSelect'}),
    )
 
    # Hidden: carries the raw 2-char prod_cat_id string, injected by JS.
    # CharField (NOT IntegerField) — MstProdCat.prod_cat_id is CharField PK.
    item_category_id = forms.CharField(
        max_length=2,
        widget=forms.HiddenInput(attrs={'id': 'itemCategoryIdHidden'}),
        required=True,
    )
 
    hsn_code = forms.CharField(
        max_length=50, required=False, label='HSN Code',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'e.g. 30049099',
            'id': 'hsnCodeInput', 'autocomplete': 'off',
        }),
    )
 
    min_level = forms.DecimalField(
        max_digits=10, decimal_places=3,
        required=False, label='Minimum Level',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input', 'placeholder': '0.000',
            'id': 'minLevelInput', 'min': '0', 'step': '0.001',
        }),
    )
 
    max_level = forms.DecimalField(
        max_digits=10, decimal_places=3,
        required=False, label='Maximum Level',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input', 'placeholder': '0.000',
            'id': 'maxLevelInput', 'min': '0', 'step': '0.001',
        }),
    )
 
    maintain_batch = forms.ChoiceField(
        choices=[('Y', 'Yes'), ('N', 'No')],
        label='Maintain Batch', initial='N',
        widget=forms.RadioSelect(attrs={'class': 'yn-radio', 'id': 'maintainBatchRadio'}),
    )
 
    mfg_date = forms.ChoiceField(
        choices=[('Y', 'Yes'), ('N', 'No')],
        label='Manufacturing Date', initial='N',
        widget=forms.RadioSelect(attrs={'class': 'yn-radio', 'id': 'mfgDateRadio'}),
    )
 
    exp_date = forms.ChoiceField(
        choices=[('Y', 'Yes'), ('N', 'No')],
        label='Expiry Date', initial='N',
        widget=forms.RadioSelect(attrs={'class': 'yn-radio', 'id': 'expDateRadio'}),
    )
 
    last_purchase_rate = forms.DecimalField(
        max_digits=12, decimal_places=2,
        initial='0.00', label='Last Purchase Rate',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input', 'placeholder': '0.00',
            'id': 'lastPurchaseRateInput', 'min': '0', 'step': '0.01',
        }),
    )

    sample_qty = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        initial='0.000',
        label='Sample qty',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input',
            'placeholder': '0.000',
            'id': 'sampleQtyInput',
            'min': '0',
            'step': '0.001',
        }),
    )

    uom = forms.ModelChoiceField(
        queryset=MstUom.objects.none(),
        label='UOM',
        empty_label='— Select UOM —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'itemUomSelect'}),
    )
 
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        # M2: live querysets per-request
        self.fields['item_type'].queryset = (
            MstItemType.objects.select_related('item_category').all()
        )
        self.fields['uom'].queryset = MstUom.objects.all().order_by('uom_name')
 
    # ── Field-level validation ──────────────────────────────────
 
    def clean_item_name(self):
        name = self.cleaned_data.get('item_name', '').strip()
        qs = MstItem.objects.filter(item_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Item "{name}" already exists.')
        return name
 
    def clean_item_category_id(self):
        """
        Resolve the raw 2-char string PK to a MstProdCat instance.
        Same pattern as ProductForm.clean_prod_category_id().
        """
        raw = self.cleaned_data.get('item_category_id', '').strip().upper()
        if not raw:
            raise forms.ValidationError('Item category is required.')
        try:
            return MstProdCat.objects.get(pk=raw)
        except MstProdCat.DoesNotExist:
            raise forms.ValidationError(f'Item category "{raw}" does not exist.')
 
    def clean_min_level(self):
        val = self.cleaned_data.get('min_level')
        if val is not None and val < 0:
            raise forms.ValidationError('Minimum level cannot be negative.')
        return val
 
    def clean_last_purchase_rate(self):
        val = self.cleaned_data.get('last_purchase_rate')
        if val is not None and val < 0:
            raise forms.ValidationError('Last purchase rate cannot be negative.')
        return val

    def clean_sample_qty(self):
        val = self.cleaned_data.get('sample_qty')
        if val is not None and val < 0:
            raise forms.ValidationError('Sample qty cannot be negative.')
        return val

    def clean_uom(self):
        u = self.cleaned_data.get('uom')
        if not u:
            raise forms.ValidationError('UOM is required.')
        return u
 
    # ── Cross-field validation ──────────────────────────────────
 
    def clean(self):
        cleaned = super().clean()
 
        # max_level >= min_level
        min_lvl = cleaned.get('min_level')
        max_lvl = cleaned.get('max_level')
        if min_lvl is not None and max_lvl is not None and max_lvl < min_lvl:
            self.add_error('max_level', 'Maximum level must be ≥ minimum level.')
 
        # Y/N cascade enforcement
        maintain = cleaned.get('maintain_batch', 'N')
        mfg      = cleaned.get('mfg_date', 'N')
        exp      = cleaned.get('exp_date', 'N')
 
        if maintain == 'N':
            # Force downstream flags off
            cleaned['mfg_date'] = 'N'
            cleaned['exp_date'] = 'N'
        elif mfg == 'N':
            # mfg_date off → exp_date must also be off
            cleaned['exp_date'] = 'N'
 
        return cleaned
 
    # ── Form contract ───────────────────────────────────────────
 
    def get_initial(self):
        if not self.instance:
            return {}
        inst = self.instance
        return {
            'item_name':          inst.item_name,
            'item_type':          inst.item_type,
            'item_category_id':   inst.item_category_id,   # raw 2-char PK string
            'hsn_code':           inst.hsn_code,
            'min_level':          inst.min_level,
            'max_level':          inst.max_level,
            'maintain_batch':     inst.maintain_batch,
            'mfg_date':           inst.mfg_date,
            'exp_date':           inst.exp_date,
            'last_purchase_rate': inst.last_purchase_rate,
            'sample_qty':         inst.sample_qty,
            'uom':                inst.uom,
        }
 
    def save(self):
        """
        FK assignments:
          item_type     = cd['item_type']         → MstItemType instance (ModelChoiceField)
          item_category = cd['item_category_id']  → MstProdCat instance (resolved in clean)
        """
        cd = self.cleaned_data
        fields = dict(
            item_name          = cd['item_name'],
            item_type          = cd['item_type'],           # MstItemType instance
            item_category      = cd['item_category_id'],    # MstProdCat instance
            uom                = cd['uom'],
            hsn_code           = cd.get('hsn_code') or None,
            min_level          = cd.get('min_level'),
            max_level          = cd.get('max_level'),
            maintain_batch     = cd['maintain_batch'],
            mfg_date           = cd['mfg_date'],
            exp_date           = cd['exp_date'],
            last_purchase_rate = cd['last_purchase_rate'],
            sample_qty         = cd['sample_qty'],
        )
        try:
            if self.instance:
                for attr, val in fields.items():
                    setattr(self.instance, attr, val)
                self.instance.save()
                return self.instance
            return MstItem.objects.create(**fields)
        except IntegrityError:
            raise forms.ValidationError(
                f'Item "{cd["item_name"]}" already exists '
                '(saved by another user just now).'
            )
        
# ═══════════════════════════════════════════════════════════════
#  CUSTOMER FORM — append to masters/forms.py
# ═══════════════════════════════════════════════════════════════

class CustomerForm(forms.Form):
    """
    Create / edit a Customer (MstCust) + related MstCustProd rows.

    Validation rules (mirror JS client-side checks):
      cust_name   : required, unique
      short_name  : required, unique, no spaces, max 10 chars, uppercase
      address     : required
      state       : required
      pin_code    : required, numeric, exactly 6 digits
      landline_no : numeric, exactly 10 digits (optional)
      mobile_no   : numeric, exactly 10 digits (optional)
      pan_no      : exactly 10 chars (optional)

    products_json: JSON array of product rows, validated in clean_products_json.
    """

    cust_name = forms.CharField(
        max_length=200, label='Customer Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Enter customer name',
            'id': 'custNameInput', 'autocomplete': 'off',
        }),
    )

    short_name = forms.CharField(
        max_length=10, label='Short Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Max 10 chars, no spaces',
            'id': 'shortNameInput', 'autocomplete': 'off', 'maxlength': '10',
        }),
    )

    address = forms.CharField(
        label='Address',
        widget=forms.Textarea(attrs={
            'class': 'cu-textarea', 'placeholder': 'Enter full address…',
            'id': 'addressInput', 'rows': 3,
        }),
    )

    state = forms.ModelChoiceField(
        queryset=MstState.objects.none(),
        label='State', empty_label='— Select State —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'stateSelect'}),
    )

    pin_code = forms.CharField(
        max_length=6, required=True, label='Pin Code',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '6-digit pin',
            'id': 'pinCodeInput', 'autocomplete': 'off', 'maxlength': '6',
        }),
    )

    landline_no = forms.CharField(
        max_length=10, required=False, label='Land Line No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '10-digit number',
            'id': 'landlineInput', 'autocomplete': 'off', 'maxlength': '10',
        }),
    )

    mobile_no = forms.CharField(
        max_length=10, required=False, label='Mobile No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '10-digit mobile',
            'id': 'mobileInput', 'autocomplete': 'off', 'maxlength': '10',
        }),
    )

    email = forms.CharField(
        max_length=150, required=False, label='Email ID',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'email@example.com',
            'id': 'emailInput', 'autocomplete': 'off',
        }),
    )

    pan_no = forms.CharField(
        max_length=10, required=False, label='PAN No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'ABCDE1234F',
            'id': 'panInput', 'autocomplete': 'off', 'maxlength': '10',
        }),
    )

    gst_no = forms.CharField(
        max_length=15, required=False, label='GST No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '22AAAAA0000A1Z5',
            'id': 'gstInput', 'autocomplete': 'off',
        }),
    )

    udyam_cert = forms.CharField(
        max_length=30, required=False, label='Udyam Certificate',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'UDYAM-XX-00-0000000',
            'id': 'udyamInput', 'autocomplete': 'off',
        }),
    )

    products_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'productsJsonHidden'}),
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['state'].queryset = MstState.objects.all().order_by('state_name')

    # ── Field-level validation ──────────────────────────────────

    def clean_cust_name(self):
        name = self.cleaned_data.get('cust_name', '').strip()
        qs = MstCust.objects.filter(cust_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Customer "{name}" already exists.')
        return name

    def clean_short_name(self):
        sn = self.cleaned_data.get('short_name', '').strip().upper()
        if ' ' in sn:
            raise forms.ValidationError('Short name must not contain spaces.')
        if len(sn) > 10:
            raise forms.ValidationError('Short name must be 10 characters or fewer.')
        qs = MstCust.objects.filter(short_name__iexact=sn)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Short name "{sn}" already exists.')
        return sn

    def clean_address(self):
        val = self.cleaned_data.get('address', '').strip()
        if not val:
            raise forms.ValidationError('Address must not be blank.')
        return val

    def clean_pin_code(self):
        val = self.cleaned_data.get('pin_code', '').strip()
        if not val:
            raise forms.ValidationError('Pin code is required.')
        if not val.isdigit():
            raise forms.ValidationError('Pin code must contain only digits.')
        if len(val) != 6:
            raise forms.ValidationError('Pin code must be exactly 6 digits.')
        return val

    def clean_landline_no(self):
        val = self.cleaned_data.get('landline_no', '').strip()
        if not val:
            return None
        if not val.isdigit():
            raise forms.ValidationError('Landline number must contain only digits.')
        if len(val) != 10:
            raise forms.ValidationError('Landline number must be exactly 10 digits.')
        return val

    def clean_mobile_no(self):
        val = self.cleaned_data.get('mobile_no', '').strip()
        if not val:
            return None
        if not val.isdigit():
            raise forms.ValidationError('Mobile number must contain only digits.')
        if len(val) != 10:
            raise forms.ValidationError('Mobile number must be exactly 10 digits.')
        return val

    def clean_pan_no(self):
        val = self.cleaned_data.get('pan_no', '').strip().upper()
        if not val:
            return None
        if len(val) != 10:
            raise forms.ValidationError('PAN number must be exactly 10 characters.')
        return val

    def clean_products_json(self):
        """
        Parse and validate the JSON product grid submitted from the wizard.
        Returns a validated list of dicts ready for save().
 
        BUG-FIX: previously returned [] silently when the grid was empty.
        save() would then delete all existing products and bulk_create nothing,
        wiping the customer's product list entirely.  We now require at least
        one product row so the delete+insert cycle in save() is never reached
        with an empty payload.
        """
        raw = self.cleaned_data.get('products_json', '').strip()
        if not raw or raw == '[]':
            raise forms.ValidationError(        # <── was: return []
                'At least one product is required. '
                'Please add products before saving.'
            )
 
        try:
            rows = _json.loads(raw)
        except ValueError:
            raise forms.ValidationError('Invalid product data submitted.')
 
        if not isinstance(rows, list):
            raise forms.ValidationError('Invalid product data format.')
 
        seen_prod_ids = set()
        validated     = []
 
        for i, row in enumerate(rows, start=1):
            prod_id     = row.get('prod_id')
            adv_license = str(row.get('adv_license', 'N')).upper()
            lic_details = (row.get('license_details') or '').strip()
            batch_abbr  = (row.get('batch_abbr') or '').strip().upper()
 
            if not prod_id:
                raise forms.ValidationError(f'Row {i}: product is required.')
            try:
                prod_obj = MstProd.objects.get(pk=prod_id)
            except MstProd.DoesNotExist:
                raise forms.ValidationError(f'Row {i}: product does not exist.')
 
            if prod_id in seen_prod_ids:
                raise forms.ValidationError(
                    f'Row {i}: "{prod_obj.prod_name}" is listed more than once.'
                )
            seen_prod_ids.add(prod_id)
 
            if adv_license not in ('Y', 'N'):
                adv_license = 'N'
            if adv_license == 'Y' and not lic_details:
                raise forms.ValidationError(
                    f'Row {i}: License Details required when Advance License is Y.'
                )
 
            if len(batch_abbr) != 3:
                raise forms.ValidationError(
                    f'Row {i}: Batch Abbreviation must be exactly 3 characters.'
                )
 
            validated.append({
                'product':         prod_obj,
                'adv_license':     adv_license,
                'license_details': lic_details or None,
                'batch_abbr':      batch_abbr,
            })
 
        return validated

    # ── Form contract ───────────────────────────────────────────

    def get_initial(self):
        if not self.instance:
            return {}
        inst = self.instance
        prod_rows = list(
            inst.cust_products.select_related('product').values(
                'cust_prod_id', 'product__prod_id', 'product__prod_name',
                'adv_license', 'license_details', 'batch_abbr',
            )
        )
        products_json = _json.dumps([
            {
                'cust_prod_id':    r['cust_prod_id'],
                'prod_id':         r['product__prod_id'],
                'prod_name':       r['product__prod_name'],
                'adv_license':     r['adv_license'],
                'license_details': r['license_details'] or '',
                'batch_abbr':      r['batch_abbr'],
            }
            for r in prod_rows
        ])
        return {
            'cust_name':     inst.cust_name,
            'short_name':    inst.short_name,
            'address':       inst.address,
            'state':         inst.state,
            'pin_code':      inst.pin_code,
            'landline_no':   inst.landline_no,
            'mobile_no':     inst.mobile_no,
            'email':         inst.email,
            'pan_no':        inst.pan_no,
            'gst_no':        inst.gst_no,
            'udyam_cert':    inst.udyam_cert,
            'products_json': products_json,
        }

    def save(self):
        """
        Saves MstCust + all MstCustProd rows atomically.
        On edit: deletes existing product rows and re-inserts from validated list.
        """
        cd = self.cleaned_data

        cust_fields = dict(
            cust_name   = cd['cust_name'],
            short_name  = cd['short_name'],
            address     = cd['address'],
            state       = cd['state'],
            pin_code    = cd.get('pin_code')    or None,
            landline_no = cd.get('landline_no') or None,
            mobile_no   = cd.get('mobile_no')   or None,
            email       = cd.get('email')       or None,
            pan_no      = cd.get('pan_no')      or None,
            gst_no      = cd.get('gst_no')      or None,
            udyam_cert  = cd.get('udyam_cert')  or None,
        )
        prod_rows = cd.get('products_json', [])

        try:
            with db_transaction.atomic():
                if self.instance:
                    for attr, val in cust_fields.items():
                        setattr(self.instance, attr, val)
                    self.instance.save()
                    cust = self.instance
                    cust.cust_products.all().delete()
                else:
                    cust = MstCust.objects.create(**cust_fields)

                MstCustProd.objects.bulk_create([
                    MstCustProd(
                        customer        = cust,
                        product         = row['product'],
                        adv_license     = row['adv_license'],
                        license_details = row['license_details'],
                        batch_abbr      = row['batch_abbr'],
                    )
                    for row in prod_rows
                ])
                return cust

        except IntegrityError:
            raise forms.ValidationError(
                f'Customer "{cd["cust_name"]}" already exists '
                '(saved by another user just now).'
            )


class SupplierForm(forms.Form):
    """
    Create / edit a Supplier (MstSupplier).
    Validation mirrors CustomerForm step-1 field rules (no products).
    """

    supl_name = forms.CharField(
        max_length=200, label='Supplier Name',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Enter supplier name',
            'id': 'suplNameInput', 'autocomplete': 'organization',
        }),
    )

    short_name = forms.CharField(
        max_length=10, label='Short Name',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'Max 10 chars, no spaces',
            'id': 'suppShortNameInput', 'autocomplete': 'off', 'maxlength': '10',
        }),
    )

    address = forms.CharField(
        label='Address',
        widget=forms.Textarea(attrs={
            'class': 'cu-textarea', 'placeholder': 'Enter full address…',
            'id': 'suppAddressInput', 'rows': 3,
        }),
    )

    state = forms.ModelChoiceField(
        queryset=MstState.objects.none(),
        label='State', empty_label='— Select State —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'suppStateSelect'}),
    )

    pin_code = forms.CharField(
        max_length=6, required=True, label='Pin Code',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '6-digit pin',
            'id': 'suppPinCodeInput', 'autocomplete': 'postal-code', 'maxlength': '6',
        }),
    )

    landline_no = forms.CharField(
        max_length=10, required=False, label='Land Line No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '10-digit number',
            'id': 'suppLandlineInput', 'autocomplete': 'tel', 'maxlength': '10',
        }),
    )

    mobile_no = forms.CharField(
        max_length=10, required=False, label='Mobile No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '10-digit mobile',
            'id': 'suppMobileInput', 'autocomplete': 'tel-national', 'maxlength': '10',
        }),
    )

    email = forms.CharField(
        max_length=150, required=False, label='Email ID',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'email@example.com',
            'id': 'suppEmailInput', 'autocomplete': 'email',
        }),
    )

    pan_no = forms.CharField(
        max_length=10, required=False, label='PAN No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'ABCDE1234F',
            'id': 'suppPanInput', 'autocomplete': 'off', 'maxlength': '10',
        }),
    )

    gst_no = forms.CharField(
        max_length=15, required=False, label='GST No.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': '22AAAAA0000A1Z5',
            'id': 'suppGstInput', 'autocomplete': 'off',
        }),
    )

    udyam_cert = forms.CharField(
        max_length=30, required=False, label='Udyam Certificate',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'placeholder': 'UDYAM-XX-00-0000000',
            'id': 'suppUdyamInput', 'autocomplete': 'off',
        }),
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['state'].queryset = MstState.objects.all().order_by('state_name')

    def clean_supl_name(self):
        name = self.cleaned_data.get('supl_name', '').strip()
        qs = MstSupplier.objects.filter(supl_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Supplier "{name}" already exists.')
        return name

    def clean_short_name(self):
        sn = self.cleaned_data.get('short_name', '').strip().upper()
        if not sn:
            return None
        if ' ' in sn:
            raise forms.ValidationError('Short name must not contain spaces.')
        if len(sn) > 10:
            raise forms.ValidationError('Short name must be 10 characters or fewer.')
        qs = MstSupplier.objects.filter(short_name__iexact=sn)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Short name "{sn}" already exists.')
        return sn

    def clean_address(self):
        val = self.cleaned_data.get('address', '').strip()
        if not val:
            raise forms.ValidationError('Address must not be blank.')
        return val

    def clean_pin_code(self):
        val = self.cleaned_data.get('pin_code', '').strip()
        if not val:
            raise forms.ValidationError('Pin code is required.')
        if not val.isdigit():
            raise forms.ValidationError('Pin code must contain only digits.')
        if len(val) != 6:
            raise forms.ValidationError('Pin code must be exactly 6 digits.')
        return val

    def clean_landline_no(self):
        val = self.cleaned_data.get('landline_no', '').strip()
        if not val:
            return None
        if not val.isdigit():
            raise forms.ValidationError('Landline number must contain only digits.')
        if len(val) != 10:
            raise forms.ValidationError('Landline number must be exactly 10 digits.')
        return val

    def clean_mobile_no(self):
        val = self.cleaned_data.get('mobile_no', '').strip()
        if not val:
            return None
        if not val.isdigit():
            raise forms.ValidationError('Mobile number must contain only digits.')
        if len(val) != 10:
            raise forms.ValidationError('Mobile number must be exactly 10 digits.')
        return val

    def clean_pan_no(self):
        val = self.cleaned_data.get('pan_no', '').strip().upper()
        if not val:
            return None
        if len(val) != 10:
            raise forms.ValidationError('PAN number must be exactly 10 characters.')
        return val

    def get_initial(self):
        if not self.instance:
            return {}
        inst = self.instance
        return {
            'supl_name':   inst.supl_name,
            'short_name':  inst.short_name,
            'address':     inst.address,
            'state':       inst.state,
            'pin_code':    inst.pin_code,
            'landline_no': inst.landline_no,
            'mobile_no':   inst.mobile_no,
            'email':       inst.email,
            'pan_no':      inst.pan_no,
            'gst_no':      inst.gst_no,
            'udyam_cert':  inst.udyam_cert,
        }

    def save(self):
        cd = self.cleaned_data
        fields = dict(
            supl_name   = cd['supl_name'],
            short_name  = cd.get('short_name') or None,
            address     = cd['address'],
            state       = cd['state'],
            pin_code    = cd['pin_code'],
            landline_no = cd.get('landline_no') or None,
            mobile_no   = cd.get('mobile_no') or None,
            email       = cd.get('email') or None,
            pan_no      = cd.get('pan_no') or None,
            gst_no      = cd.get('gst_no') or None,
            udyam_cert  = cd.get('udyam_cert') or None,
        )
        try:
            if self.instance:
                for attr, val in fields.items():
                    setattr(self.instance, attr, val)
                self.instance.save()
                return self.instance
            return MstSupplier.objects.create(**fields)
        except IntegrityError:
            raise forms.ValidationError(
                f'Supplier "{cd["supl_name"]}" already exists '
                '(saved by another user just now).'
            )


class BomRmForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select Customer —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomRmCustomerSelect'})
    )
    product = forms.ModelChoiceField(
        queryset=MstProd.objects.none(),
        label='Product',
        empty_label='— Select Product —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomRmProductSelect'})
    )
    machine = forms.ModelChoiceField(
        queryset=MstMachine.objects.none(),
        label='Machine',
        empty_label='— Select Machine —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomRmMachineSelect'})
    )
    no_of_lots = forms.IntegerField(
        required=True,
        min_value=1,
        label='No of Lots',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'bomRmNoOfLotsInput', 'min': '1'})
    )
    shape = forms.ModelChoiceField(
        queryset=MstShape.objects.none(),
        required=False,
        label='Shape',
        empty_label='— Select Shape —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomRmShapeSelect'})
    )
    color = forms.ModelChoiceField(
        queryset=MstColor.objects.none(),
        required=False,
        label='Color',
        empty_label='— Select Color —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomRmColorSelect'})
    )
    coating = forms.ModelChoiceField(
        queryset=MstCoatType.objects.none(),
        required=False,
        label='Coating',
        empty_label='— Select Coating —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomRmCoatingSelect'})
    )
    capsule = forms.ModelChoiceField(
        queryset=MstCapsule.objects.none(),
        required=False,
        label='Capsule',
        empty_label='— Select Capsule —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomRmCapsuleSelect'})
    )
    avg_wt = forms.IntegerField(
        required=True,
        min_value=1,
        label='Average Weight (mg)',
        widget=forms.NumberInput(attrs={'class': 'cu-input', 'id': 'bomRmAvgWtInput', 'min': '1'})
    )
    batch_size = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label='Batch size (lakh)',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input', 'id': 'bomBatchSizeInput', 'step': '0.01', 'min': '0.01',
        }),
    )
    batch_nos = forms.CharField(
        required=False,
        label='Batch nos.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'id': 'bomBatchNosInput', 'readonly': 'readonly', 'tabindex': '-1',
        }),
    )
    items_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'bomItemsJsonHidden'})
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')
        self.fields['product'].queryset = MstProd.objects.none()
        self.fields['machine'].queryset = MstMachine.objects.filter(section_id__in=[2,5]).order_by('machine_name')
        self.fields['shape'].queryset = MstShape.objects.all().order_by('shape_name')
        self.fields['color'].queryset = MstColor.objects.all().order_by('color_name')
        self.fields['coating'].queryset = MstCoatType.objects.all().order_by('coating_name')
        self.fields['capsule'].queryset = MstCapsule.objects.all().order_by('capsule_name')

        cust_id = None
        if self.instance and getattr(self.instance, 'customer_id', None):
            cust_id = self.instance.customer_id
        else:
            raw = self.data.get('customer') if hasattr(self, 'data') else None
            try:
                cust_id = int(raw) if raw else None
            except (TypeError, ValueError):
                cust_id = None
        self.fields['product'].queryset = _bom_products_for_customer(cust_id)

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        product = cleaned.get('product')
        machine = cleaned.get('machine')
        if not product:
            return cleaned
        if customer and not MstCustProd.objects.filter(customer=customer, product=product).exists():
            self.add_error('product', 'Select a product mapped to the selected customer.')
            return cleaned
        prod_type = (getattr(product, 'prod_type', None).item_type_name or '').strip().lower()
        if not cleaned.get('no_of_lots'):
            self.add_error('no_of_lots', 'No of Lot is Required.')
        if prod_type == 'tablet':
            cleaned['capsule'] = None
        if prod_type == 'capsule':
            cleaned['shape'] = None
            cleaned['color'] = None
            cleaned['coating'] = None
            if not cleaned.get('capsule'):
                self.add_error('capsule', 'Capsule is required for capsule products.')
        if not cleaned.get('avg_wt'):
            self.add_error('avg_wt', 'Average weight is required.')
        bs = cleaned.get('batch_size')
        if bs is not None:
            cleaned['batch_nos'] = _bom_batch_nos_from_lakh(bs)
        return cleaned

    def clean_items_json(self):
        raw = (self.cleaned_data.get('items_json') or '').strip()
        if not raw or raw == '[]':
            raise forms.ValidationError('At least one item row is required.')
        try:
            rows = _json.loads(raw)
        except ValueError:
            raise forms.ValidationError('Invalid item grid data submitted.')
        if not isinstance(rows, list):
            raise forms.ValidationError('Invalid item grid format.')
        seen = set()
        validated = []
        for idx, row in enumerate(rows, start=1):
            stage_id = row.get('stage_id')
            item_id = row.get('item_id')
            qty = row.get('qty')
            if not stage_id or not item_id:
                raise forms.ValidationError(f'Row {idx}: stage and item are required.')
            key = (int(stage_id), int(item_id))
            if key in seen:
                raise forms.ValidationError(f'Row {idx}: duplicate stage + item combination.')
            seen.add(key)
            try:
                stage = MstPdnStage.objects.get(pk=stage_id)
                item = MstItem.objects.select_related('uom').get(pk=item_id)
            except (MstPdnStage.DoesNotExist, MstItem.DoesNotExist):
                raise forms.ValidationError(f'Row {idx}: invalid stage or item.')
            if item.uom_id is None:
                raise forms.ValidationError(
                    f'Row {idx}: item "{item.item_name}" has no UOM. Set UOM on the Item master first.'
                )
            try:
                qty_val = float(qty)
            except (TypeError, ValueError):
                raise forms.ValidationError(f'Row {idx}: qty must be numeric.')
            if qty_val <= 0:
                raise forms.ValidationError(f'Row {idx}: qty must be greater than 0.')

            validated.append({
                'stage': stage,
                'item': item,
                'qty': qty_val,
                'uom': item.uom,
            })
        return validated

    def get_initial(self):
        if not self.instance:
            return {}
        rows = list(
            self.instance.items.select_related('stage', 'item', 'uom').all()
        )
        return {
            'customer': self.instance.customer,
            'product': self.instance.product,
            'machine' : self.instance.machine_id,
            'no_of_lots' : self.instance.no_of_lots,
            'shape': self.instance.shape,
            'color': self.instance.color,
            'coating': self.instance.coating,
            'capsule': self.instance.capsule,
            'avg_wt': self.instance.avg_wt,
            'batch_size': self.instance.batch_size,
            'batch_nos': self.instance.batch_nos,
            'items_json': _json.dumps([
                {
                    'stage_id': r.stage_id,
                    'stage_name': r.stage.stage_name,
                    'item_id': r.item_id,
                    'item_name': r.item.item_name,
                    'qty': str(r.qty),
                    'uom_id': r.uom_id,
                    'uom_name': r.uom.short_name,
                }
                for r in rows
            ])
        }

    def save(self):
        cd = self.cleaned_data
        if self.instance and self.instance.is_locked:
            raise forms.ValidationError('This BOM is locked and cannot be edited.')
        spec_name = cd['customer'].short_name
        product = cd['product']
        prod_type_name = getattr(product.prod_type, 'item_type_name', '')
        parts = [spec_name, prod_type_name]
        if cd.get('machine'):
            parts.append(cd['machine'].machine_name)
        if cd.get('shape'):
            parts.append(cd['shape'].shape_name)
        if cd.get('color'):
            parts.append(cd['color'].color_name)
        if cd.get('coating'):
            parts.append(cd['coating'].coating_name)
        if cd.get('capsule'):
            parts.append(cd['capsule'].capsule_name)
        if cd.get('avg_wt'):
            parts.append(f"{cd['avg_wt']}mg")
        full_spec = ' / '.join([p for p in parts if p])
        try:
            with db_transaction.atomic():
                fields = dict(
                    spec_name=full_spec, customer=cd['customer'], product=product,
                    machine=cd.get('machine'), no_of_lots=cd.get('no_of_lots'),
                    shape=cd.get('shape'), color=cd.get('color'),
                    coating=cd.get('coating'), capsule=cd.get('capsule'),
                    avg_wt=cd.get('avg_wt'),
                    batch_size=cd['batch_size'],
                    batch_nos=cd['batch_nos'],
                )
                if self.instance:
                    for k, v in fields.items():
                        setattr(self.instance, k, v)
                    self.instance.save()
                    obj = self.instance
                    obj.items.all().delete()
                else:
                    obj = MstBomRmHed.objects.create(**fields)
                MstBomRmDtl.objects.bulk_create([
                    MstBomRmDtl(
                        spec=obj,
                        stage=r['stage'],
                        item=r['item'],
                        qty=r['qty'],
                        uom=r['uom'],
                    )
                    for r in cd['items_json']
                ])
                return obj
        except IntegrityError:
            raise forms.ValidationError('BOM RM with this specification already exists.')


class BomPmForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=MstCust.objects.none(),
        label='Customer',
        empty_label='— Select Customer —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomPmCustomerSelect'})
    )
    product = forms.ModelChoiceField(
        queryset=MstProd.objects.none(),
        label='Product',
        empty_label='— Select Product —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomPmProductSelect'})
    )
    pkg_style = forms.ModelChoiceField(
        queryset=MstPkgStyle.objects.none(),
        label='Packing Style',
        empty_label='— Select Packing Style —',
        widget=forms.Select(attrs={'class': 'cu-select searchable-dropdown', 'id': 'bomPmPkgStyleSelect'})
    )
    batch_size = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label='Batch size (lakh)',
        widget=forms.NumberInput(attrs={
            'class': 'cu-input', 'id': 'bomBatchSizeInput', 'step': '0.01', 'min': '0.01',
        }),
    )
    batch_nos = forms.CharField(
        required=False,
        label='Batch nos.',
        widget=forms.TextInput(attrs={
            'class': 'cu-input', 'id': 'bomBatchNosInput', 'readonly': 'readonly', 'tabindex': '-1',
        }),
    )
    items_json = forms.CharField(required=False, widget=forms.HiddenInput(attrs={'id': 'bomItemsJsonHidden'}))

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = MstCust.objects.all().order_by('cust_name')
        self.fields['product'].queryset = MstProd.objects.none()
        self.fields['pkg_style'].queryset = MstPkgStyle.objects.select_related('pkg_type').all().order_by('pkg_style_name')

        cust_id = None
        if self.instance and getattr(self.instance, 'customer_id', None):
            cust_id = self.instance.customer_id
        else:
            raw = self.data.get('customer') if hasattr(self, 'data') else None
            try:
                cust_id = int(raw) if raw else None
            except (TypeError, ValueError):
                cust_id = None
        self.fields['product'].queryset = _bom_products_for_customer(cust_id)

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        product = cleaned.get('product')
        if customer and product and not MstCustProd.objects.filter(customer=customer, product=product).exists():
            self.add_error('product', 'Select a product mapped to the selected customer.')
        bs = cleaned.get('batch_size')
        if bs is not None:
            cleaned['batch_nos'] = _bom_batch_nos_from_lakh(bs)
        return cleaned

    def clean_items_json(self):
        return BomRmForm.clean_items_json(self)

    def get_initial(self):
        if not self.instance:
            return {}
        rows = list(self.instance.items.select_related('stage', 'item', 'uom').all())
        return {
            'customer': self.instance.customer,
            'product': self.instance.product,
            'pkg_style': self.instance.pkg_style,
            'batch_size': self.instance.batch_size,
            'batch_nos': self.instance.batch_nos,
            'items_json': _json.dumps([
                {'stage_id': r.stage_id, 'stage_name': r.stage.stage_name, 'item_id': r.item_id, 'item_name': r.item.item_name, 'qty': str(r.qty), 'uom_id': r.uom_id, 'uom_name': r.uom.short_name}
                for r in rows
            ])
        }

    def save(self):
        cd = self.cleaned_data
        if self.instance and self.instance.is_locked:
            raise forms.ValidationError('This BOM is locked and cannot be edited.')
        full_spec = f"{cd['customer'].short_name} / {cd['pkg_style'].pkg_style_name}"
        try:
            with db_transaction.atomic():
                fields = dict(
                    spec_name=full_spec,
                    customer=cd['customer'],
                    product=cd['product'],
                    pkg_style=cd['pkg_style'],
                    batch_size=cd['batch_size'],
                    batch_nos=cd['batch_nos'],
                )
                if self.instance:
                    for k, v in fields.items():
                        setattr(self.instance, k, v)
                    self.instance.save()
                    obj = self.instance
                    obj.items.all().delete()
                else:
                    obj = MstBomPmHed.objects.create(**fields)
                MstBomPmDtl.objects.bulk_create([
                    MstBomPmDtl(spec=obj, stage=r['stage'], item=r['item'], qty=r['qty'], uom=r['uom'])
                    for r in cd['items_json']
                ])
                return obj
        except IntegrityError:
            raise forms.ValidationError('BOM PM with this combination already exists.')