from django.urls import path

from . import views

app_name = 'transactions'

urlpatterns = [
    path('transactions/inward/', views.inward_view, name='inward'),
    path('transactions/inward/<int:pk>/delete/', views.inward_delete_view, name='inward_delete'),
    path('transactions/ajax/inward-items/', views.inward_items_ajax, name='inward_items_ajax'),
    path('transactions/ajax/inward-item-meta/', views.inward_item_meta_ajax, name='inward_item_meta_ajax'),
    path('transactions/ajax/inward-next-numbers/', views.inward_next_numbers_ajax, name='inward_next_numbers_ajax'),
    path('api/suggest-grn/', views.SuggestGRNView.as_view(), name='suggest_grn_api'),
    path('transactions/sales-order/', views.sales_order_view, name='sales_order'),
    path('transactions/sales-order/<int:pk>/delete/', views.sales_order_delete_view, name='sales_order_delete'),
    path(
        'transactions/ajax/sales-order-product-meta/',
        views.sales_order_product_meta_ajax,
        name='sales_order_product_meta_ajax',
    ),
    
    path(
        'transactions/ajax/sales-order-customer-products/',
        views.sales_order_customer_products_ajax,
        name='sales_order_customer_products_ajax',
    ),
    path('transactions/sales-invoice/', views.sales_invoice_view, name='sales_invoice'),
    path(
        'transactions/sales-invoice/<int:pk>/delete/',
        views.sales_invoice_delete_view,
        name='sales_invoice_delete',
    ),
    path(
        'transactions/ajax/sales-invoice/next-numbers/',
        views.sales_invoice_next_numbers_ajax,
        name='sales_invoice_next_numbers_ajax',
    ),
    path(
        'transactions/ajax/sales-invoice/orders/',
        views.sales_invoice_orders_ajax,
        name='sales_invoice_orders_ajax',
    ),
    path(
        'transactions/ajax/sales-invoice/fg-batches/',
        views.sales_invoice_fg_batches_ajax,
        name='sales_invoice_fg_batches_ajax',
    ),
    path(
        'transactions/ajax/sales-invoice/order-detail/',
        views.sales_invoice_order_detail_ajax,
        name='sales_invoice_order_detail_ajax',
    ),
    path(
        'transactions/ajax/sales-invoice/order-products/',
        views.sales_invoice_order_products_ajax,
        name='sales_invoice_order_products_ajax',
    ),
    path('transactions/batch-allocation/', views.batch_allocation_view, name='batch_allocation'),
    path(
        'transactions/ajax/batch-allocation/orders/',
        views.batch_allocation_orders_ajax,
        name='batch_allocation_orders_ajax',
    ),
    path(
        'transactions/ajax/batch-allocation/order-detail/',
        views.batch_allocation_order_detail_ajax,
        name='batch_allocation_order_detail_ajax',
    ),
    path(
        'transactions/ajax/batch-allocation/products/',
        views.batch_allocation_products_ajax,
        name='batch_allocation_products_ajax',
    ),
    path(
        'transactions/ajax/batch-allocation/previous-batches/',
        views.batch_allocation_previous_batches_ajax,
        name='batch_allocation_previous_batches_ajax',
    ),
    path('transactions/log-sheet/', views.log_sheet_view, name='log_sheet'),
    path(
        'transactions/ajax/logsheet/customer-products/',
        views.logsheet_customer_products_ajax,
        name='logsheet_customer_products_ajax',
    ),
    path(
        'transactions/ajax/logsheet/pending-batches/',
        views.logsheet_pending_batches_ajax,
        name='logsheet_pending_batches_ajax',
    ),
    path(
        'transactions/ajax/logsheet/product-meta/',
        views.logsheet_product_meta_ajax,
        name='logsheet_product_meta_ajax',
    ),
    path(
        'transactions/ajax/logsheet/list/',
        views.logsheet_list_ajax,
        name='logsheet_list_ajax',
    ),
    path('transactions/rm-dispensing/', views.rm_dispensing_view, name='rm_dispensing'),
    path(
        'transactions/ajax/rm-dispensing/customer-products/',
        views.rm_dispensing_customer_products_ajax,
        name='rm_dispensing_customer_products_ajax',
    ),
    path(
        'transactions/ajax/rm-dispensing/batches/',
        views.rm_dispensing_batches_ajax,
        name='rm_dispensing_batches_ajax',
    ),
    path(
        'transactions/ajax/rm-dispensing/specs/',
        views.rm_dispensing_specs_ajax,
        name='rm_dispensing_specs_ajax',
    ),
    path(
        'transactions/ajax/rm-dispensing/bom-items/',
        views.rm_dispensing_bom_items_ajax,
        name='rm_dispensing_bom_items_ajax',
    ),
    path(
        'transactions/ajax/rm-dispensing/list/',
        views.rm_dispensing_list_ajax,
        name='rm_dispensing_list_ajax',
    ),
    path('transactions/dpr/', views.dpr_view, name='dpr'),
    path('transactions/ajax/dpr/machines/', views.dpr_machines_ajax, name='dpr_machines_ajax'),
    path('transactions/ajax/dpr/operators/', views.dpr_operators_ajax, name='dpr_operators_ajax'),
    path(
        'transactions/ajax/dpr/customer-products/',
        views.dpr_customer_products_ajax,
        name='dpr_customer_products_ajax',
    ),
    path('transactions/ajax/dpr/logsheets/', views.dpr_logsheets_ajax, name='dpr_logsheets_ajax'),
    path('transactions/ajax/dpr/specs/', views.dpr_specs_ajax, name='dpr_specs_ajax'),
    path(
        'transactions/ajax/dpr/section-status/',
        views.dpr_section_status_ajax,
        name='dpr_section_status_ajax',
    ),
    path('transactions/ajax/dpr/list/', views.dpr_list_ajax, name='dpr_list_ajax'),
    path('transactions/daily-packing-contractors/', views.pkg_cont_view, name='pkg_cont'),
    path(
        'transactions/daily-packing-contractors/<int:pk>/delete/',
        views.pkg_cont_delete_view,
        name='pkg_cont_delete',
    ),
    path(
        'transactions/ajax/pkg-cont/products/',
        views.pkg_cont_products_ajax,
        name='pkg_cont_products_ajax',
    ),
    path(
        'transactions/ajax/pkg-cont/styles/',
        views.pkg_cont_styles_ajax,
        name='pkg_cont_styles_ajax',
    ),
    path(
        'transactions/ajax/pkg-cont/list/',
        views.pkg_cont_list_ajax,
        name='pkg_cont_list_ajax',
    ),
]

