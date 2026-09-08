from django.contrib import admin

from .models import (
    InvCustMonthlyStock,
    InventoryStock,
    TrnStkAdjDtl1,
    TrnStkAdjDtl2,
    TrnStkAdjHed,
)


@admin.register(InvCustMonthlyStock)
class InvCustMonthlyStockAdmin(admin.ModelAdmin):
    list_display = (
        'inv_mth_id',
        'cust_product',
        'year',
        'month',
        'opening_qty_lac',
        'receipt_qty_lac',
        'issue_qty_lac',
    )
    list_filter = ('year', 'month')
    search_fields = ('cust_product__customer__cust_name', 'cust_product__product__prod_name')


@admin.register(InventoryStock)
class InventoryStockAdmin(admin.ModelAdmin):
    list_display = (
        'inv_id',
        'customer',
        'product',
        'item',
        'item_category',
        'batch_no',
        'qty',
        'reserved_qty',
        'is_closed',
        'opened_in_fy',
        'last_trn_date',
        'last_trn_type',
    )
    list_filter = ('item_category', 'last_trn_type', 'is_closed')
    search_fields = (
        'customer__cust_name',
        'product__prod_name',
        'item__item_name',
        'batch_no',
    )
    raw_id_fields = ('customer', 'product', 'item', 'item_category', 'opened_in_fy')


class TrnStkAdjDtl1Inline(admin.TabularInline):
    model = TrnStkAdjDtl1
    extra = 0
    raw_id_fields = ('product', 'item')


@admin.register(TrnStkAdjHed)
class TrnStkAdjHedAdmin(admin.ModelAdmin):
    list_display = ('stk_adj_id', 'stk_adj_dt', 'customer', 'stk_adj_type', 'item_type')
    list_filter = ('stk_adj_type',)
    search_fields = ('customer__cust_name', 'remarks')
    raw_id_fields = ('customer', 'item_type')
    inlines = (TrnStkAdjDtl1Inline,)


@admin.register(TrnStkAdjDtl1)
class TrnStkAdjDtl1Admin(admin.ModelAdmin):
    list_display = ('dtl1_id', 'header', 'product', 'item', 'quantity', 'line_remarks')
    raw_id_fields = ('header', 'product', 'item')


@admin.register(TrnStkAdjDtl2)
class TrnStkAdjDtl2Admin(admin.ModelAdmin):
    list_display = ('dtl2_id', 'line', 'batch_no', 'mfg_date', 'exp_date', 'batch_qty')
    raw_id_fields = ('line',)
