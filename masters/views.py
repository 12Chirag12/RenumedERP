"""
masters/views.py

════════════════════════════════════════════════════════════════
 FORM CONTRACT  (what each form in forms.py must implement)
════════════════════════════════════════════════════════════════
Every form must expose two methods so that views.py stays free
of per-entity field knowledge:

    def get_initial(self) -> dict
        Returns {field_name: value} to pre-fill the form on GET
        when self.instance is set (edit mode).
        Must return {} when self.instance is None.

    def save(self) -> model instance
        Called after form.is_valid() on POST.
        self.instance set   → update that record, return it.
        self.instance None  → create a new record, return it.
        Optional CharField fields that map to nullable DB columns
        must be coerced here:  cd.get('make') or None

════════════════════════════════════════════════════════════════
 VIEW PATTERNS
════════════════════════════════════════════════════════════════
Type B — Single combined create/edit view, ?edit_pk= query param.
         Delegated entirely to combined_view().
         Every entity now uses this pattern.

Type C — Single combined view, multiple entity types via ?type=.
         Config-dict driven — adding a type = 1 dict entry.
         Used by: ProductAttr (colour/shape/coating/category/capsule)
                  Logistics  (transporter/state)
"""

import json as _json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .forms import (
    SectionForm, MachineForm, OperatorForm, UomForm,
    StateForm, TransporterForm, ProdStageForm, ItemTypeForm,
    ColorForm, ShapeForm, CoatTypeForm, ProdCatForm, CapsuleForm,
    PkgStyleForm, ExpensesForm, ProductForm, ItemForm, CustomerForm, SupplierForm,
    BomRmForm, BomPmForm
)
from .models import (
    MstSection, MstMachine, MstOperator, MstUom, MstState,
    MstTransport, MstPdnStage, MstItemType,
    MstColor, MstShape, MstCoatType, MstProdCat, MstCapsule,
    MstPkgStyle, MstExpenses, MstExpGroup, MstProd, MstItem, MstCust, MstSupplier, MstCustProd,
    MstBomRmHed, MstBomPmHed
    
)
from .constants import get_departments


# ════════════════════════════════════════════════════════════════
#  LAYER 1 — INFRASTRUCTURE
#  Written once.  Every current and future view uses these.
# ════════════════════════════════════════════════════════════════

def get_instance(model, pk):
    """
    Return get_object_or_404(model, pk=pk) when pk is truthy, else None.
    Centralises the ?edit_pk= lookup used by every combined create/edit view.
    """
    return get_object_or_404(model, pk=pk) if pk else None


def delete_object(request, model, pk, redirect_name, name_attr):
    """
    Generic POST-only delete handler with ProtectedError handling.

    On a FK constraint violation Django raises ProtectedError instead of
    silently cascading (because all FK fields use on_delete=PROTECT).
    This helper catches that and shows a user-friendly flash message that
    names the blocking model types instead of crashing with a 500.
    """
    if request.method == 'POST':
        obj  = get_object_or_404(model, pk=pk)
        name = getattr(obj, name_attr)
        try:
            obj.delete()
            messages.success(request, f'"{name}" deleted successfully.')
        except ProtectedError as e:
            blocking = ', '.join(
                sorted({rel.__class__.__name__ for rel in e.protected_objects})
            )
            messages.error(
                request,
                f'Cannot delete "{name}" — it is referenced by: {blocking}.',
            )
    return redirect(redirect_name)


def _validated_type(value, config, default):
    """
    Return value when it is a recognised key in config, else default.
    Eliminates the repeated  if x not in CONFIG: x = 'default'  pattern.
    """
    return value if value in config else default


def combined_view(request, model, form_class, template,
                  list_key, redirect_name,
                  queryset=None, extra_context=None):
    """
    Full GET/POST cycle for any entity that uses the ?edit_pk= pattern.

    GET  → blank form on create, or form.get_initial()-prefilled on edit.
    POST → form.save() on valid submission; re-render with errors otherwise.

    model         — Django model class.
    form_class    — must implement get_initial() and save().
    list_key      — template context key for the record list, e.g. 'sections'.
    queryset      — explicit queryset when the model has FK relations the
                    template accesses, to prevent N+1 queries.
    extra_context — zero-argument callable that returns a dict of additional
                    template context.  Called on every request (GET and POST)
                    so it is always fresh.
                    e.g. extra_context=lambda: {'departments': get_departments()}

    edit_pk is read from the query string AND the POST body so that edit
    mode survives the form submission regardless of whether the template
    sets the form action to include the query string.
    """
    edit_pk  = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_instance(model, edit_pk)

    if request.method == 'POST':
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Saved successfully.')
            return redirect(redirect_name)
    else:
        form = form_class(instance=instance)
        if instance:
            form.initial = form.get_initial()

    qs  = queryset if queryset is not None else model.objects.all()
    ctx = {'form': form, list_key: qs, 'edit_instance': instance}
    if extra_context:
        ctx.update(extra_context())
    return render(request, template, ctx)


# ════════════════════════════════════════════════════════════════
#  SECTION
# ════════════════════════════════════════════════════════════════

@login_required
def section_view(request):
    return combined_view(
        request, MstSection, SectionForm,
        'masters/section_form.html', 'sections', 'section',
        queryset=MstSection.objects.select_related('department').all(),
        extra_context=lambda: {'departments': get_departments()},
    )


@login_required
def section_delete_view(request, pk):
    return delete_object(request, MstSection, pk, 'section', 'section_name')


# ════════════════════════════════════════════════════════════════
#  MACHINE
# ════════════════════════════════════════════════════════════════

@login_required
def machine_view(request):
    return combined_view(
        request, MstMachine, MachineForm,
        'masters/machine_form.html', 'machines', 'machine',
        queryset=MstMachine.objects.select_related('section__department').all(),
    )


@login_required
def machine_delete_view(request, pk):
    return delete_object(request, MstMachine, pk, 'machine', 'machine_name')


# ════════════════════════════════════════════════════════════════
#  OPERATOR
# ════════════════════════════════════════════════════════════════

@login_required
def operator_view(request):
    return combined_view(
        request,
        MstOperator,
        OperatorForm,
        'masters/operator_form.html',
        'operators',
        'operator',
        queryset=MstOperator.objects.prefetch_related(
            'section_links__section__department',
        ).all(),
    )


@login_required
def operator_delete_view(request, pk):
    return delete_object(request, MstOperator, pk, 'operator', 'opt_name')


# ── AJAX: resolve department label for a section ──────────────────────────────

@login_required
@require_GET
def get_section_department(request):
    """Return dept_name for a section_id — consumed by the machine-form JS."""
    section_id = request.GET.get('section_id')
    if not section_id:
        return JsonResponse({'dept_name': ''})
    try:
        section = MstSection.objects.select_related('department').get(pk=section_id)
        return JsonResponse({'dept_name': section.department.dept_name})
    except MstSection.DoesNotExist:
        return JsonResponse({'dept_name': ''})


# ════════════════════════════════════════════════════════════════
#  UOM
# ════════════════════════════════════════════════════════════════

@login_required
def uom_view(request):
    return combined_view(
        request, MstUom, UomForm,
        'masters/uom_form.html', 'uoms', 'uom',
    )


@login_required
def uom_delete_view(request, pk):
    return delete_object(request, MstUom, pk, 'uom', 'uom_name')


# ════════════════════════════════════════════════════════════════
#  PRODUCTION STAGE
# ════════════════════════════════════════════════════════════════

@login_required
def prod_stage_view(request):
    return combined_view(
        request, MstPdnStage, ProdStageForm,
        'masters/prod_stage_form.html', 'stages', 'prod_stage',
    )


@login_required
def prod_stage_delete_view(request, pk):
    return delete_object(request, MstPdnStage, pk, 'prod_stage', 'stage_name')


# ════════════════════════════════════════════════════════════════
#  ITEM TYPE
# ════════════════════════════════════════════════════════════════

@login_required
def item_type_view(request):
    return combined_view(
        request, MstItemType, ItemTypeForm,
        'masters/item_type_form.html', 'item_types', 'item_type',
        queryset=MstItemType.objects.select_related('item_category').all(),
    )


@login_required
def item_type_delete_view(request, pk):
    return delete_object(request, MstItemType, pk, 'item_type', 'item_type_name')

# ════════════════════════════════════════════════════════════════
#  ITEM
# ════════════════════════════════════════════════════════════════

@login_required
def item_view(request):
    """
    Type-B combined create/edit view for MstItem.
    Uses combined_view() — no file upload needed.
    item_category_id (hidden field) is in request.POST so combined_view
    passes it through to ItemForm without any custom handling.
    """
    return combined_view(
        request, MstItem, ItemForm,
        'masters/item_form.html', 'items', 'item',
        queryset=MstItem.objects.select_related(
            'item_type', 'item_category', 'uom'
        ).all(),
    )


@login_required
def item_delete_view(request, pk):
    return delete_object(request, MstItem, pk, 'item', 'item_name')

# ════════════════════════════════════════════════════════════════
#  PACKING STYLE
# ════════════════════════════════════════════════════════════════

@login_required
def pkg_style_view(request):
    return combined_view(
        request, MstPkgStyle, PkgStyleForm,
        'masters/pkg_style_form.html', 'pkg_styles', 'pkg_style',
        queryset=MstPkgStyle.objects.select_related('pkg_type').all(),
    )


@login_required
def pkg_style_delete_view(request, pk):
    return delete_object(request, MstPkgStyle, pk, 'pkg_style', 'pkg_style_name')


# ════════════════════════════════════════════════════════════════
#  EXPENSES
# ════════════════════════════════════════════════════════════════

@login_required
def expenses_view(request):
    return combined_view(
        request, MstExpenses, ExpensesForm,
        'masters/expenses_form.html', 'expenses', 'expenses',
    )


@login_required
def expenses_delete_view(request, pk):
    return delete_object(request, MstExpenses, pk, 'expenses', 'exp_name')


# ════════════════════════════════════════════════════════════════
#  TYPE C — PRODUCT ATTRIBUTES
#  Config-driven.  ?type= selects the active attribute entity.
#  Adding a new attribute type = one new ATTR_CONFIG entry, zero view edits.
# ════════════════════════════════════════════════════════════════

ATTR_CONFIG = {
    'colour':   {'model': MstColor,    'form': ColorForm,    'label': 'Colour Name',   'icon': 'palette'},
    'shape':    {'model': MstShape,    'form': ShapeForm,    'label': 'Shape Name',    'icon': 'pentagon'},
    'coating':  {'model': MstCoatType, 'form': CoatTypeForm, 'label': 'Coating Type',  'icon': 'layers'},
    'category': {'model': MstProdCat,  'form': ProdCatForm,  'label': 'Category Name', 'icon': 'tag'},
    'capsule':  {'model': MstCapsule,  'form': CapsuleForm,  'label': 'Capsule Type',  'icon': 'capsule'},
}


def _get_attr_records(attr_type):
    """Serialisable record list for the given attribute type (view + AJAX)."""
    cfg = ATTR_CONFIG.get(attr_type)
    if not cfg:
        return []
    if attr_type == 'category':
        return list(MstProdCat.objects.values('prod_cat_id', 'prod_cat_name'))
    if attr_type == 'capsule':
        return list(MstCapsule.objects.values(
            'capsule_id', 'capsule_name', 'capsule_size', 'capsule_color',
        ))
    return list(cfg['model'].objects.values())


@login_required
def product_attr_view(request):
    """
    Handles create, edit, and list for all five product attribute types
    through a single URL (?type= selects entity, ?edit_pk= triggers edit).
    """
    attr_type = _validated_type(request.GET.get('type', 'colour'), ATTR_CONFIG, 'colour')
    cfg       = ATTR_CONFIG[attr_type]

    # Read edit_pk from GET (initial load) OR POST body (form submission).
    edit_pk       = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    edit_instance = get_instance(cfg['model'], edit_pk)

    if request.method == 'POST':
        post_type = _validated_type(
            request.POST.get('attr_type', attr_type), ATTR_CONFIG, 'colour',
        )
        cfg  = ATTR_CONFIG[post_type]
        form = cfg['form'](request.POST, instance=edit_instance)

        if form.is_valid():
            form.save()
            messages.success(request, 'Record saved successfully.')
            return redirect(f"{request.path}?type={post_type}")

        # Form invalid — stay on the submitted type for re-render.
        attr_type = post_type
        cfg       = ATTR_CONFIG[attr_type]

    else:
        form = cfg['form'](instance=edit_instance)
        if edit_instance:
            form.initial = form.get_initial()

    return render(request, 'masters/product_attr_form.html', {
        'attr_type':     attr_type,
        'attr_config':   ATTR_CONFIG,
        'form':          form,
        'edit_instance': edit_instance,
        'records':       _get_attr_records(attr_type),
    })


@login_required
def product_attr_delete_view(request, attr_type, pk):
    """
    Delete a single product attribute record.

    ProtectedError is caught explicitly (C1) — previously this view called
    .delete() bare, crashing with a 500 when a referenced record (e.g. a
    product category with item types) was targeted.
    """
    if attr_type not in ATTR_CONFIG:
        return redirect('product_attr')
    if request.method == 'POST':
        obj = get_object_or_404(ATTR_CONFIG[attr_type]['model'], pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Record deleted successfully.')
        except ProtectedError as e:
            blocking = ', '.join(
                sorted({rel.__class__.__name__ for rel in e.protected_objects})
            )
            messages.error(
                request,
                f'Cannot delete this record — it is referenced by: {blocking}.',
            )
    return redirect(f"/masters/product-attributes/?type={attr_type}")


@login_required
@require_GET
def product_attr_records_ajax(request):
    """Reload table rows for a given attribute type — called by the tab JS."""
    attr_type = request.GET.get('type', 'colour')
    if attr_type not in ATTR_CONFIG:
        return JsonResponse({'records': [], 'attr_type': attr_type})
    return JsonResponse({'records': _get_attr_records(attr_type), 'attr_type': attr_type})


# ════════════════════════════════════════════════════════════════
#  TYPE C — LOGISTICS  (Transporter + State combined)
#  Config-driven.  ?type= selects the active logistics entity.
#  Adding a new logistics type = one new LOGISTICS_CONFIG entry, zero view edits.
# ════════════════════════════════════════════════════════════════

LOGISTICS_CONFIG = {
    'transporter': {
        'model': MstTransport,
        'form':  TransporterForm,
        'label': 'Transporter',
        'icon':  'bi-truck',
    },
    'state': {
        'model': MstState,
        'form':  StateForm,
        'label': 'State',
        'icon':  'bi-geo-alt-fill',
    },
}


def _get_logistics_records(ltype):
    if ltype == 'transporter':
        return list(MstTransport.objects.values('transport_id', 'transport_name'))
    if ltype == 'state':
        return list(MstState.objects.values('state_id', 'state_name', 'gst_code'))
    return []


@login_required
def logistics_view(request):
    """
    Handles create and edit for all logistics types through a single URL.
    ?type= selects the entity; edit_pk travels via GET and POST body.
    """
    ltype         = _validated_type(request.GET.get('type', 'transporter'), LOGISTICS_CONFIG, 'transporter')
    edit_pk       = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    edit_instance = None

    if request.method == 'POST':
        post_type     = _validated_type(
            request.POST.get('ltype', ltype), LOGISTICS_CONFIG, 'transporter',
        )
        cfg           = LOGISTICS_CONFIG[post_type]
        edit_instance = get_instance(cfg['model'], edit_pk)
        form          = cfg['form'](request.POST, instance=edit_instance)

        if form.is_valid():
            form.save()
            messages.success(request, f'{cfg["label"]} saved successfully.')
            return redirect(f"{request.path}?type={post_type}")

        ltype = post_type

    else:
        cfg           = LOGISTICS_CONFIG[ltype]
        edit_instance = get_instance(cfg['model'], edit_pk)
        form          = cfg['form'](instance=edit_instance)
        if edit_instance:
            form.initial = form.get_initial()

    return render(request, 'masters/logistics_form.html', {
        'ltype':         ltype,
        'form':          form,
        'edit_instance': edit_instance,
        'records':       _get_logistics_records(ltype),
    })


@login_required
def logistics_delete_view(request, ltype, pk):
    """
    Delete a single logistics record.

    ProtectedError is caught explicitly (C1) — previously this view called
    .delete() bare, crashing with a 500 when a referenced record was targeted.
    """
    if request.method == 'POST' and ltype in LOGISTICS_CONFIG:
        obj = get_object_or_404(LOGISTICS_CONFIG[ltype]['model'], pk=pk)
        try:
            obj.delete()
            messages.success(request, 'Record deleted.')
        except ProtectedError as e:
            blocking = ', '.join(
                sorted({rel.__class__.__name__ for rel in e.protected_objects})
            )
            messages.error(
                request,
                f'Cannot delete this record — it is referenced by: {blocking}.',
            )
    return redirect(f'/masters/logistics/?type={ltype}')


@login_required
@require_GET
def logistics_records_ajax(request):
    """Reload table rows for a given logistics type — called by the tab JS."""
    ltype = request.GET.get('type', 'transporter')
    return JsonResponse({'records': _get_logistics_records(ltype), 'ltype': ltype})


# ════════════════════════════════════════════════════════════════
#  PRODUCT VIEWS  (extend below as needed)
# ════════════════════════════════════════════════════════════════

@login_required
def product_view(request):
    """
    Type-B combined create/edit view for MstProd.
 
    Differences from standard combined_view():
    - Handles file upload (request.FILES) so cannot use the generic helper.
    - Passes image_file to form.save() for filesystem write + path storage.
    - AJAX endpoint /masters/ajax/item-type-category/ resolves category for
      the JS dropdown interaction.
    """
    edit_pk  = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_instance(MstProd, edit_pk)
 
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            image_file = request.FILES.get('product_image') or None
            form.save(image_file=image_file)
            messages.success(request, 'Product saved successfully.')
            return redirect('product')
    else:
        form = ProductForm(instance=instance)
        if instance:
            form.initial = form.get_initial()
 
    products = MstProd.objects.select_related(
        'prod_type', 'prod_category', 'uom', 'first_color', 'second_color'
    ).all()
 
    return render(request, 'masters/product_form.html', {
        'form':          form,
        'products':      products,
        'edit_instance': instance,
    })
 
 
@login_required
def product_delete_view(request, pk):
    return delete_object(request, MstProd, pk, 'product', 'prod_name')
 
 
@login_required
@require_GET
def get_item_type_category(request):
    """
    AJAX: return the product category for a given item_type_id.
    Called by the product-form JS when the Product Type dropdown changes.
    Response: { prod_cat_id, prod_cat_name } or { error }
    """
    item_type_id = request.GET.get('item_type_id')
    if not item_type_id:
        return JsonResponse({'error': 'item_type_id required'}, status=400)
    try:
        item_type = MstItemType.objects.select_related('item_category').get(
            pk=item_type_id
        )
        cat = item_type.item_category
        return JsonResponse({
            'prod_cat_id':   cat.prod_cat_id,
            'prod_cat_name': cat.prod_cat_name,
        })
    except MstItemType.DoesNotExist:
        return JsonResponse({'error': 'Item type not found'}, status=404)


# ════════════════════════════════════════════════════════════════
#  CUSTOMER
# ════════════════════════════════════════════════════════════════

@login_required
def customer_view(request):
    """
    Combined create / edit for MstCust + MstCustProd.

    This is a two-step wizard (step 1 = customer details, step 2 = product
    grid) and needs careful error handling that combined_view() cannot
    provide:

      • save() may raise ValidationError (race-condition IntegrityError
        caught and re-raised inside the form) — we must catch it here and
        feed it back as a non-field error instead of letting it crash to 500.

      • products_json is a hidden field — its validation errors would be
        invisible unless we explicitly pop them and pass them as a separate
        context variable for the step-2 error banner.

      • When the only errors are on products (step 2), the page must auto-
        advance past step 1 so the user actually sees them.

      • The raw POST value of products_json is run through json.loads →
        json.dumps to sanitise it before injecting into the template with
        |safe.
    """
    edit_pk  = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    instance = get_instance(MstCust, edit_pk)
    start_step = 1                  # which wizard step to show on render

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=instance)
        if form.is_valid():
            # ── FIX 1: catch ValidationError from save() ──────────
            # save() wraps IntegrityError as ValidationError when a
            # concurrent duplicate insert beats us.  Previously this
            # was uncaught → 500.
            try:
                form.save()
                messages.success(request, 'Customer saved successfully.')
                return redirect('customer')
            except ValidationError as exc:
                form.add_error(None, exc)

        # ── FIX 2 + 3: pop hidden-field errors, compute start_step ──
        # products_json errors live in form.errors['products_json'] but
        # the hidden field has no visible rendering.  Pop them so they
        # can be shown in the step-2 error banner.
        product_errors = form.errors.pop('products_json', [])

        # After popping product errors, whatever remains belongs to
        # step-1 fields (or non-field errors from the save() catch).
        has_step1_errors = bool(form.errors) or bool(form.non_field_errors())
        if not has_step1_errors and product_errors:
            start_step = 2          # jump straight to step 2

        # ── FIX 5: sanitise raw POST JSON before template injection ──
        raw = request.POST.get('products_json', '[]')
        try:
            parsed = _json.loads(raw)
            if not isinstance(parsed, list):
                parsed = []
        except (ValueError, TypeError):
            parsed = []
        existing_prods_json = _json.dumps(parsed)

    else:
        form = CustomerForm(instance=instance)
        if instance:
            form.initial = form.get_initial()
        existing_prods_json = form.initial.get('products_json', '[]')
        product_errors = []

    customers = MstCust.objects.select_related('state').all()
    products_list = list(
        MstProd.objects.values('prod_id', 'prod_name').order_by('prod_name')
    )

    return render(request, 'masters/customer_form.html', {
        'form':                form,
        'customers':           customers,
        'edit_instance':       instance,
        'products_json':       _json.dumps(products_list),
        'existing_prods_json': existing_prods_json,
        'product_errors':      product_errors,    # FIX 2: visible in step 2
        'start_step':          start_step,         # FIX 3: JS reads this
    })
 


@login_required
def customer_delete_view(request, pk):
    return delete_object(request, MstCust, pk, 'customer', 'cust_name')


@login_required
def supplier_view(request):
    return combined_view(
        request, MstSupplier, SupplierForm,
        'masters/supplier_form.html', 'suppliers', 'supplier',
        queryset=MstSupplier.objects.select_related('state').all(),
    )


@login_required
def supplier_delete_view(request, pk):
    return delete_object(request, MstSupplier, pk, 'supplier', 'supl_name')


@login_required
@require_GET
def customer_products_ajax(request):
    """
    AJAX: return product rows for a customer (used if needed for async reload).
    /masters/ajax/customer-products/?cust_id=N
    """
    cust_id = request.GET.get('cust_id')
    if not cust_id:
        return JsonResponse({'rows': []})
    rows = list(
        MstCustProd.objects.filter(customer_id=cust_id)
        .select_related('product')
        .values(
            'cust_prod_id', 'product__prod_id', 'product__prod_name',
            'adv_license', 'license_details', 'batch_abbr',
        )
    )
    return JsonResponse({'rows': [
        {
            'cust_prod_id':    r['cust_prod_id'],
            'prod_id':         r['product__prod_id'],
            'prod_name':       r['product__prod_name'],
            'adv_license':     r['adv_license'],
            'license_details': r['license_details'] or '',
            'batch_abbr':      r['batch_abbr'],
        }
        for r in rows
    ]})


def _get_bom_records(bom_type):
    if bom_type == 'pm':
        return list(
            MstBomPmHed.objects.select_related('customer', 'product', 'pkg_style')
            .annotate(num_items=Count('items'))
            .values(
                'spec_id', 'spec_name',
                'customer__cust_name', 'product__prod_name',
                'pkg_style__pkg_style_name', 'is_locked', 'num_items',
            )
        )
    return list(
        MstBomRmHed.objects.select_related('customer', 'product')
        .annotate(num_items=Count('items'))
        .values(
            'spec_id', 'spec_name',
            'customer__cust_name', 'product__prod_name',
            'is_locked', 'num_items',
        )
    )


@login_required
def bom_view(request):
    start_step = 1
    bom_type = request.GET.get('type', 'rm')
    if bom_type not in ('rm', 'pm'):
        bom_type = 'rm'
    edit_pk = request.GET.get('edit_pk') or request.POST.get('edit_pk')
    model = MstBomRmHed if bom_type == 'rm' else MstBomPmHed
    form_class = BomRmForm if bom_type == 'rm' else BomPmForm
    instance = get_instance(model, edit_pk)

    if request.method == 'POST':
        post_type = request.POST.get('bom_type', bom_type)
        if post_type in ('rm', 'pm'):
            bom_type = post_type
        model = MstBomRmHed if bom_type == 'rm' else MstBomPmHed
        form_class = BomRmForm if bom_type == 'rm' else BomPmForm
        if edit_pk:
            instance = get_instance(model, edit_pk)
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'BOM saved successfully.')
                return redirect(f"{request.path}?type={bom_type}")
            except ValidationError as exc:
                form.add_error(None, exc)
        item_errors = form.errors.pop('items_json', [])
        has_step1_errors = bool(form.errors) or bool(form.non_field_errors())
        if not has_step1_errors and item_errors:
            start_step = 2
        raw_items = request.POST.get('items_json', '[]')
        try:
            parsed_items = _json.loads(raw_items)
            if not isinstance(parsed_items, list):
                parsed_items = []
        except (ValueError, TypeError):
            parsed_items = []
        existing_items_json = _json.dumps(parsed_items)
    else:
        form = form_class(instance=instance)
        if instance:
            form.initial = form.get_initial()
        existing_items_json = form.initial.get('items_json', '[]')
        item_errors = []

    # Filter item dropdown list by BOM type:
    # - rm: raw material items only
    # - pm: packing material items only
    # We support both ID-based (RM/PM) and name-based (contains "raw"/"pack") categories
    # so this works across different master-data naming conventions.
    items_qs = MstItem.objects.select_related('uom', 'item_category').order_by('item_name')
    if bom_type == 'rm':
        filtered = items_qs.filter(
            Q(item_category__prod_cat_id__iexact='RM') |
            Q(item_category__prod_cat_name__icontains='raw')
        )
        if filtered.exists():
            items_qs = filtered
    else:
        filtered = items_qs.filter(
            Q(item_category__prod_cat_id__iexact='PM') |
            Q(item_category__prod_cat_name__icontains='pack')
        )
        if filtered.exists():
            items_qs = filtered

    context = {
        'form': form,
        'bom_type': bom_type,
        'edit_instance': instance,
        'records': _get_bom_records(bom_type),
        'customers_json': _json.dumps(list(MstCust.objects.values('cust_id', 'cust_name', 'short_name').order_by('cust_name'))),
        'products_json': _json.dumps(list(MstProd.objects.select_related('prod_type').values('prod_id', 'prod_name', 'prod_type__item_type_name').order_by('prod_name'))),
        'stages_json': _json.dumps(list(MstPdnStage.objects.values('stage_id', 'stage_name').order_by('stage_name'))),
        'items_json': _json.dumps(list(items_qs.values('item_id', 'item_name', 'uom_id', 'uom__short_name'))),
        'shapes_json': _json.dumps(list(MstShape.objects.values('shape_id', 'shape_name').order_by('shape_name'))),
        'colors_json': _json.dumps(list(MstColor.objects.values('color_id', 'color_name').order_by('color_name'))),
        'coatings_json': _json.dumps(list(MstCoatType.objects.values('coating_id', 'coating_name').order_by('coating_name'))),
        'capsules_json': _json.dumps(list(MstCapsule.objects.values('capsule_id', 'capsule_name').order_by('capsule_name'))),
        'pkg_styles_json': _json.dumps(list(MstPkgStyle.objects.values('pkg_style_id', 'pkg_style_name').order_by('pkg_style_name'))),
        'machines_json': _json.dumps(list(
            MstMachine.objects.select_related('section').values(
                'machine_id', 'machine_name', 'section_id', 'section__section_name',
            ).order_by('machine_name')
        )) if bom_type == 'rm' else '[]',
        'existing_items_json': existing_items_json,
        'item_errors': item_errors,
        'start_step': start_step,
    }
    return render(request, 'masters/bom_form.html', context)


@login_required
def bom_delete_view(request, bom_type, pk):
    if bom_type == 'pm':
        return delete_object(request, MstBomPmHed, pk, 'bom', 'spec_name')
    return delete_object(request, MstBomRmHed, pk, 'bom', 'spec_name')


@login_required
@require_GET
def bom_records_ajax(request):
    bom_type = request.GET.get('type', 'rm')
    if bom_type not in ('rm', 'pm'):
        bom_type = 'rm'
    return JsonResponse({'records': _get_bom_records(bom_type), 'type': bom_type})


@login_required
@require_GET
def item_uom_ajax(request):
    item_id = request.GET.get('item_id')
    if not item_id:
        return JsonResponse({'uom_id': None, 'uom_name': ''})
    try:
        item = MstItem.objects.select_related('uom').get(pk=item_id)
        if not item.uom_id:
            return JsonResponse({'uom_id': None, 'uom_name': '', 'error': 'Item has no UOM set.'})
        return JsonResponse({'uom_id': item.uom_id, 'uom_name': item.uom.short_name})
    except MstItem.DoesNotExist:
        return JsonResponse({'uom_id': None, 'uom_name': ''})


@login_required
@require_GET
def product_type_ajax(request):
    prod_id = request.GET.get('prod_id')
    if not prod_id:
        return JsonResponse({'product_type': ''})
    try:
        prod = MstProd.objects.select_related('prod_type').get(pk=prod_id)
        return JsonResponse({'product_type': prod.prod_type.item_type_name})
    except MstProd.DoesNotExist:
        return JsonResponse({'product_type': ''})