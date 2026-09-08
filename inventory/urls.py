from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'inventory'

urlpatterns = [
    path(
        'inventory/customer-monthly/',
        RedirectView.as_view(pattern_name='inventory:inventory_stock', permanent=False),
        name='customer_monthly_redirect',
    ),
    path(
        'inventory/stock/',
        views.inventory_stock_view,
        name='inventory_stock',
    ),
    path(
        'inventory/ajax/stock-lifecycle/',
        views.inventory_stock_lifecycle_ajax,
        name='inventory_stock_lifecycle_ajax',
    ),
    path(
        'inventory/stock-adjustment/',
        views.stock_adjustment_view,
        name='stock_adjustment',
    ),
    path(
        'inventory/ajax/stock-adj-masters/',
        views.stock_adjustment_masters_ajax,
        name='stock_adj_masters_ajax',
    ),
    path(
        'inventory/ajax/stock-adj-sku-meta/',
        views.stock_adjustment_sku_meta_ajax,
        name='stock_adj_sku_meta_ajax',
    ),
    path(
        'inventory/ajax/stock-adj-inv-defaults/',
        views.stock_adjustment_inv_defaults_ajax,
        name='stock_adj_inv_defaults_ajax',
    ),
]
