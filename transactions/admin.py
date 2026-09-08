from django.contrib import admin

from .models import (
    TrnBatchDtl,
    TrnBatchHed,
    TrnDpr,
    TrnDprInputBatch,
    TrnInwDtl1,
    TrnInwDtl2,
    TrnInwHed,
    TrnLogSheet,
    TrnPkgCont,
    TrnSlsDtl1,
    TrnSlsDtl2,
    TrnSlsHed,
    TrnSlsOrdDtl1,
    TrnSlsOrdDtl2,
    TrnSlsOrdHed,
)


class TrnInwDtl1Inline(admin.TabularInline):
    model = TrnInwDtl1
    extra = 0


@admin.register(TrnInwHed)
class TrnInwHedAdmin(admin.ModelAdmin):
    list_display = (
        'inward_id', 'inward_dt', 'grn_no', 'grn_category',
        'customer', 'supplier', 'inv_no', 'documents',
    )
    list_filter = ('inward_dt', 'grn_category')
    search_fields = ('grn_no', 'register_no', 'inv_no')
    inlines = [TrnInwDtl1Inline]


@admin.register(TrnInwDtl2)
class TrnInwDtl2Admin(admin.ModelAdmin):
    list_display = ('dtl2_id', 'inward', 'item', 'batch_no', 'arn_no', 'batch_qty', 'product')
    list_filter = ('inward',)


class TrnSlsOrdDtl1Inline(admin.TabularInline):
    model = TrnSlsOrdDtl1
    extra = 0


@admin.register(TrnSlsOrdHed)
class TrnSlsOrdHedAdmin(admin.ModelAdmin):
    list_display = (
        'order_id', 'ord_rec_dt', 'customer', 'cust_ord_id', 'taxable_val', 'total_amt', 'document_path',
    )
    list_filter = ('ord_rec_dt',)
    search_fields = ('cust_ord_id',)
    inlines = [TrnSlsOrdDtl1Inline]


@admin.register(TrnSlsOrdDtl2)
class TrnSlsOrdDtl2Admin(admin.ModelAdmin):
    list_display = ('dtl2_id', 'order', 'product', 'disp_sche_dt', 'disp_qty')
    list_filter = ('order',)


class TrnSlsDtl1Inline(admin.TabularInline):
    model = TrnSlsDtl1
    extra = 0
    raw_id_fields = ('order_line',)


@admin.register(TrnSlsHed)
class TrnSlsHedAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_id', 'invoice_no', 'invoice_dt', 'customer', 'transporter',
        'reference_order', 'taxable_val', 'total_amt', 'created_at',
    )
    list_filter = ('invoice_dt',)
    search_fields = ('invoice_no',)
    inlines = [TrnSlsDtl1Inline]


@admin.register(TrnSlsDtl2)
class TrnSlsDtl2Admin(admin.ModelAdmin):
    list_display = ('dtl2_id', 'invoice_line', 'log_sheet', 'batch_qty')
    list_filter = ('invoice_line__invoice',)
    raw_id_fields = ('invoice_line', 'log_sheet')


class TrnBatchDtlInline(admin.TabularInline):
    model = TrnBatchDtl
    extra = 0


@admin.register(TrnBatchHed)
class TrnBatchHedAdmin(admin.ModelAdmin):
    list_display = (
        'batch_id',
        'customer',
        'order',
        'product',
        'batch_abbr',
        'batch_from',
        'batch_to',
        'partial_yn',
    )
    list_filter = ('partial_yn',)
    search_fields = ('batch_abbr',)
    inlines = [TrnBatchDtlInline]


@admin.register(TrnBatchDtl)
class TrnBatchDtlAdmin(admin.ModelAdmin):
    list_display = ('dtl_id', 'batch', 'batch_no', 'batch_qty_l', 'batch_qty_n', 'mfg_dt', 'exp_dt')
    search_fields = ('batch_no',)


class TrnDprInputBatchInline(admin.TabularInline):
    model = TrnDprInputBatch
    extra = 0
    raw_id_fields = ('log_sheet',)


@admin.register(TrnDpr)
class TrnDprAdmin(admin.ModelAdmin):
    list_display = (
        'trn_dpr_id',
        'trn_dpr_dt',
        'section',
        'machine',
        'shift_id',
        'machine_working',
        'customer',
        'product',
        'batch_line',
        'qty_nos',
    )
    list_filter = ('trn_dpr_dt', 'shift_id', 'machine_working', 'section')
    search_fields = ('remarks', 'batch_line__batch_no', 'operator1__opt_name', 'operator2__opt_name')
    inlines = [TrnDprInputBatchInline]


@admin.register(TrnPkgCont)
class TrnPkgContAdmin(admin.ModelAdmin):
    list_display = (
        'pkgcont_id',
        'pkgcont_date',
        'contractor',
        'log_sheet',
        'pkg_style',
        'shipper_no',
        'qty_nos',
    )
    list_filter = ('pkgcont_date',)
    search_fields = ('remarks', 'contractor__opt_name', 'log_sheet__batch_line__batch_no')


@admin.register(TrnLogSheet)
class TrnLogSheetAdmin(admin.ModelAdmin):
    list_display = (
        'logsheet_id',
        'gran_dt',
        'section',
        'shift_id',
        'customer',
        'product',
        'batch_line_no',
        'layer_slot',
        'blend_dt',
        'dpr_flg',
    )
    list_filter = ('gran_dt', 'shift_id', 'section')
    search_fields = ('batch_line__batch_no',)

    @admin.display(description='Batch no.')
    def batch_line_no(self, obj):
        return obj.batch_line.batch_no if obj.batch_line_id else ''
