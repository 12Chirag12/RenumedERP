from django.contrib import admin

from .models import (
    InvCustMonthlyStock,
    InventoryStock,
    StockDtl,
    StockHed,
    TrnStkAdjDtl1,
    TrnStkAdjDtl2,
    TrnStkAdjHed,
)


class StockDtlInline(admin.TabularInline):
    model = StockDtl
    extra = 0
    readonly_fields = (
        'tran_id',
        'trn_type',
        'trn_no',
        'trn_date',
        'quantity',
        'source_line_id',
        'is_reversal',
        'reversal_of',
        'created_at',
    )
    can_delete = False


@admin.register(StockHed)
class StockHedAdmin(admin.ModelAdmin):
    list_display = (
        'stock_lnkno',
        'financial_year',
        'customer',
        'product',
        'item',
        'batch_no',
        'opn_qty',
        'rcpt_qty',
        'issue_qty',
        'closing_qty',
        'is_closed',
        'last_trn_date',
        'last_trn_type',
    )
    list_filter = ('financial_year', 'is_closed', 'item_category')
    search_fields = (
        'customer__cust_name',
        'product__prod_name',
        'item__item_name',
        'batch_no',
    )
    raw_id_fields = ('customer', 'product', 'item', 'item_category', 'financial_year')
    readonly_fields = ('closing_qty', 'created_at', 'updated_at')
    inlines = (StockDtlInline,)


@admin.register(StockDtl)
class StockDtlAdmin(admin.ModelAdmin):
    list_display = (
        'stock_dtl_id',
        'stock',
        'tran_id',
        'trn_type',
        'trn_no',
        'trn_date',
        'quantity',
        'source_line_id',
        'is_reversal',
        'reversal_of',
        'created_at',
    )
    list_filter = ('tran_id', 'trn_type', 'is_reversal', 'trn_date')
    search_fields = (
        'trn_no',
        'source_line_id',
        'remarks',
        'stock__customer__cust_name',
        'stock__product__prod_name',
        'stock__item__item_name',
    )
    raw_id_fields = ('stock', 'reversal_of')
    readonly_fields = (
        'stock',
        'tran_id',
        'trn_type',
        'trn_no',
        'trn_date',
        'quantity',
        'source_line_id',
        'is_reversal',
        'reversal_of',
        'created_at',
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
