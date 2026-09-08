"""
masters/urls.py

Changes from previous version:
  — Removed section_edit, machine_edit, uom_edit URL patterns.
    All three entities now use the ?edit_pk= query param pattern
    handled by their single combined view.
"""

from django.urls import path
from . import views

urlpatterns = [
    # ── Section ───────────────────────────────────────────────────
    path('masters/section/',
         views.section_view,name='section'),
    path('masters/section/<int:pk>/delete/',
         views.section_delete_view, name='section_delete'),

    # ── Machine ───────────────────────────────────────────────────
    path('masters/machine/',
         views.machine_view, name='machine'),
    path('masters/machine/<int:pk>/delete/',
         views.machine_delete_view, name='machine_delete'),

    # ── Operator ───────────────────────────────────────────────────
    path('masters/operator/',
         views.operator_view, name='operator'),
    path('masters/operator/<int:pk>/delete/',
         views.operator_delete_view, name='operator_delete'),

    path('masters/ajax/section-dept/', 
         views.get_section_department, name='section_dept_ajax'),

    # ── UOM ───────────────────────────────────────────────────────
    path('masters/uom/', 
         views.uom_view, name='uom'),
    path('masters/uom/<int:pk>/delete/', 
         views.uom_delete_view, name='uom_delete'),

    # ── Product attributes ────────────────────────────────────────
    path('masters/product-attributes/',
         views.product_attr_view, name='product_attr'),
    path('masters/product-attributes/<str:attr_type>/<pk>/delete/',
         views.product_attr_delete_view, name='product_attr_delete'),
    path('masters/ajax/product-attr-records/',
         views.product_attr_records_ajax, name='product_attr_records_ajax'),

    # ── Logistics (Transporter + State combined) ──────────────────
    path('masters/logistics/',
         views.logistics_view, name='logistics'),
    path('masters/logistics/<str:ltype>/<pk>/delete/',
         views.logistics_delete_view, name='logistics_delete'),
    path('masters/ajax/logistics-records/',
         views.logistics_records_ajax, name='logistics_records_ajax'),

    # ── Production Stage ──────────────────────────────────────────
    path('masters/prod-stage/',
         views.prod_stage_view, name='prod_stage'),
    path('masters/prod-stage/<int:pk>/delete/',
         views.prod_stage_delete_view, name='prod_stage_delete'),

    # ── Item Type ─────────────────────────────────────────────────
    path('masters/item-type/',
         views.item_type_view, name='item_type'),
    path('masters/item-type/<int:pk>/delete/',
         views.item_type_delete_view, name='item_type_delete'),

    # ── Packing Style ─────────────────────────────────────────────
    path('masters/packing-style/',
         views.pkg_style_view, name='pkg_style'),
    path('masters/packing-style/<int:pk>/delete/',
         views.pkg_style_delete_view, name='pkg_style_delete'),

    # ── Expenses ──────────────────────────────────────────────────
    path('masters/expenses/',
         views.expenses_view, name='expenses'),
    path('masters/expenses/<int:pk>/delete/',
         views.expenses_delete_view, name='expenses_delete'),

     # ── Product ───────────────────────────────────────────────────
     path('masters/product/',                 
          views.product_view, name='product'),
     path('masters/product/<int:pk>/delete/', 
          views.product_delete_view, name='product_delete'),
     path('masters/ajax/item-type-category/', 
          views.get_item_type_category, name='item_type_category_ajax'),

     # ── Item ──────────────────────────────────────────────────────
     path('masters/item/',                 
          views.item_view, name='item'),
     path('masters/item/<int:pk>/delete/', 
          views.item_delete_view, name='item_delete'),

          
     # ── Customer ──────────────────────────────────────────────────
     path('masters/customer/',
          views.customer_view, name='customer'),
     path('masters/customer/<int:pk>/delete/', 
          views.customer_delete_view, name='customer_delete'),
     path('masters/ajax/customer-products/', 
          views.customer_products_ajax, name='customer_products_ajax'),

     # ── Supplier ──────────────────────────────────────────────────
     path('masters/supplier/',
          views.supplier_view, name='supplier'),
     path('masters/supplier/<int:pk>/delete/',
          views.supplier_delete_view, name='supplier_delete'),

     # ── BOM ───────────────────────────────────────────────────────
     path('masters/bom/',
          views.bom_view, name='bom'),
     path('masters/bom/<str:bom_type>/<int:pk>/delete/',
          views.bom_delete_view, name='bom_delete'),
     path('masters/ajax/bom-records/',
          views.bom_records_ajax, name='bom_records_ajax'),
     path('masters/ajax/item-uom/',
          views.item_uom_ajax, name='item_uom_ajax'),
     path('masters/ajax/product-type/',
          views.product_type_ajax, name='product_type_ajax'),
]