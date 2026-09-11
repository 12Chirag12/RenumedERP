"""
Transaction models — Inward (RM/PM).

Spec tables TrnInwHed / TrnInwDtl1 / TrnInwDtl2 map to masters:
- Customer (MstCust), Supplier (mstSupplier), Transporter (MstTransport)
- GRN category = MstProdCat (RM / PM — 2-char prod_cat_id)
- Item batch behaviour = MstItem.maintain_batch ('Y' / 'N')

Database CHECK constraints mirror business rules so invalid rows are rejected even
outside the Django form (admin, scripts). Model.clean() + save(full_clean) adds
cross-field checks (e.g. batch lines tied to Dtl1).
"""

from decimal import ROUND_FLOOR, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

import re

from .utils import get_or_create_financial_year_for_date

from .constants import (
    GRN_CATEGORY_IDS,
    GRN_NO_PATTERN,
    GST_TYPE_CHOICES,
    GST_TYPE_CGST_SGST,
    GST_TYPE_EXEMPTED,
    GST_TYPE_IDS,
    GST_TYPE_IGST,
    INVOICE_NO_PATTERN,
    QTY_DECIMAL_PLACES,
    REGISTER_NO_PATTERN,
    SO_QTY_DECIMAL_PLACES,
)


class TrnInwHed(models.Model):
    """Header for one inward (GRN) transaction."""

    inward_id = models.AutoField(primary_key=True)
    inward_dt = models.DateField(verbose_name='Inward Date')

    # Financial year tracking (backend only).
    financial_year = models.ForeignKey(
        'masters.FinancialYear',
        on_delete=models.PROTECT,
        db_column='fy_id',
        related_name='inwards',
        verbose_name='Financial Year',
        editable=False,
    )
    working_year = models.CharField(
        max_length=9,  # "2025-26"
        db_index=True,
        editable=False,
        verbose_name='Financial Year',
    )

    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='inwards',
        verbose_name='Customer',
    )

    register_no = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Register No.',
        help_text='Format: R- plus digits (e.g. R-00001 … R-99999, then R-100000).',
        validators=[
            RegexValidator(
                REGISTER_NO_PATTERN,
                _('Must match R- plus digits (e.g. R-00001 or R-100000).'),
            ),
        ],
    )

    grn_category = models.ForeignKey(
        'masters.MstProdCat',
        on_delete=models.PROTECT,
        db_column='grn_prod_cat_id',
        related_name='inwards',
        verbose_name='GRN Type (RM / PM)',
    )

    grn_no = models.CharField(
        max_length=50,
        verbose_name='GRN No.',
        help_text='Format RM-… or PM-… (shared sequence; e.g. RM-00001 … RM-100000).',
    )

    supplier = models.ForeignKey(
        'masters.MstSupplier',
        on_delete=models.PROTECT,
        db_column='supl_id',
        related_name='inwards',
        verbose_name='Supplier',
    )

    inv_no = models.CharField(max_length=100, verbose_name='Invoice No.')
    inv_dt = models.DateField(verbose_name='Invoice Date')

    transporter = models.ForeignKey(
        'masters.MstTransport',
        on_delete=models.PROTECT,
        db_column='transport_id',
        related_name='inwards',
        verbose_name='Transporter',
    )

    vehicle_no = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Vehicle No.',
    )
    driver_name = models.CharField(
        max_length=150, blank=True, null=True, verbose_name='Driver Name',
    )
    driver_no = models.CharField(
        max_length=30, blank=True, null=True, verbose_name='Driver Contact',
    )
    remarks = models.TextField(blank=True, null=True, verbose_name='Remarks')

    documents = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='Documents',
        help_text='Relative path under MEDIA_ROOT for the uploaded header document (PDF/image).',
    )

    class Meta:
        db_table = 'TrnInwHed'
        verbose_name = 'Inward (Header)'
        verbose_name_plural = 'Inwards (Headers)'
        ordering = ['-inward_dt', '-inward_id']
        constraints = [
            models.UniqueConstraint(
                fields=['grn_no', 'financial_year'],
                name='unique_grn_per_fy',
            ),
            models.CheckConstraint(
                condition=models.Q(inv_dt__lte=models.F('inward_dt')),
                name='trn_inw_hed_inv_dt_lte_inward_dt',
            ),
            models.CheckConstraint(
                condition=models.Q(grn_category_id__in=list(GRN_CATEGORY_IDS)),
                name='trn_inw_hed_grn_cat_rm_or_pm',
            ),
        ]

    def __str__(self):
        return f"Inward {self.inward_id} — GRN {self.grn_no}"

    def clean(self):
        super().clean()
        if self.register_no:
            self.register_no = self.register_no.strip().upper()
        if self.vehicle_no is not None:
            self.vehicle_no = str(self.vehicle_no).strip()
        if self.inv_dt and self.inward_dt and self.inv_dt > self.inward_dt:
            raise ValidationError({'inv_dt': _('Invoice date must not be after inward date.')})
        if self.grn_category_id and self.grn_category_id not in GRN_CATEGORY_IDS:
            raise ValidationError({'grn_category': _('GRN type must be RM or PM.')})
        if self.grn_no and self.grn_category_id:
            g = (self.grn_no or '').strip().upper()
            if not re.fullmatch(GRN_NO_PATTERN, g):
                raise ValidationError(
                    {'grn_no': _('Must match RM-… or PM-… (prefix plus digits, e.g. RM-100000).')}
                )
            prefix = g.split('-')[0]
            if prefix != str(self.grn_category_id).upper():
                raise ValidationError({'grn_no': _('GRN no. prefix must match the selected GRN type.')})

    def save(self, *args, **kwargs):
        if self.inward_dt:
            # Ensure FY row exists (e.g. new FY on 1-Apr) without requiring admin UI or seed first.
            fy = get_or_create_financial_year_for_date(self.inward_dt)
            self.financial_year = fy
            self.working_year = fy.fy_display
        self.full_clean()
        super().save(*args, **kwargs)


class TrnInwDtl1(models.Model):
    """One line per item and total quantity for an inward."""

    dtl1_id = models.AutoField(primary_key=True)
    inward = models.ForeignKey(
        TrnInwHed,
        on_delete=models.CASCADE,
        db_column='inward_id',
        related_name='lines',
    )
    item = models.ForeignKey(
        'masters.MstItem',
        on_delete=models.PROTECT,
        db_column='item_id',
        related_name='inward_lines',
    )
    pkg_style = models.CharField(
        max_length=30,
        verbose_name='Pkg_Style',
        blank=True,
        help_text='Free-text packing style for this item line.',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=QTY_DECIMAL_PLACES,
        verbose_name='Quantity',
    )
    uom = models.ForeignKey(
        'masters.MstUom',
        on_delete=models.PROTECT,
        db_column='uom_id',
        related_name='inward_lines',
        verbose_name='UOM',
    )
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Rate',
    )

    class Meta:
        db_table = 'TrnInwDtl1'
        verbose_name = 'Inward Item Line'
        verbose_name_plural = 'Inward Item Lines'
        constraints = [
            models.UniqueConstraint(
                fields=['inward', 'item'],
                name='unique_trn_inw_item_dtl1',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='trn_inw_dtl1_quantity_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gte=0),
                name='trn_inw_dtl1_rate_non_negative',
            ),
        ]

    def __str__(self):
        return f"Inward {self.inward_id} item {self.item_id} qty {self.quantity}"

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': _('Quantity must be greater than zero.')})
        if self.rate is not None and self.rate < 0:
            raise ValidationError({'rate': _('Rate cannot be negative.')})
        if self.item_id and self.uom_id and self.item and self.item.uom_id:
            if self.uom_id != self.item.uom_id:
                raise ValidationError(
                    {'uom': _('UOM must match the item master UOM for this item.')}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnInwDtl2(models.Model):
    """Batch-level split for one item line (only when item.maintain_batch = Y)."""

    dtl2_id = models.AutoField(primary_key=True)
    inward = models.ForeignKey(
        TrnInwHed,
        on_delete=models.CASCADE,
        db_column='inward_id',
        related_name='batch_lines',
    )
    item = models.ForeignKey(
        'masters.MstItem',
        on_delete=models.PROTECT,
        db_column='item_id',
        related_name='inward_batches',
    )
    batch_no = models.CharField(max_length=100, verbose_name='Batch No.')
    arn_no = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='ARN no.',
    )

    pack_style = models.CharField(
        max_length=30,
        db_column='pkg_style_id',
        verbose_name='Packing Style',
        help_text='Free-text packing style for this batch line.',
    )

    mfg_dt = models.DateField(
        blank=True,
        null=True,
        verbose_name='Manufacturing Date',
    )
    exp_dt = models.DateField(
        blank=True,
        null=True,
        verbose_name='Expiry Date',
    )
    batch_qty = models.DecimalField(
        max_digits=14,
        decimal_places=QTY_DECIMAL_PLACES,
        verbose_name='Batch Qty',
    )

    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        related_name='inward_batches',
        verbose_name='Product',
        blank=True,
        null=True,
    )

    class Meta:
        db_table = 'TrnInwDtl2'
        verbose_name = 'Inward Batch Line'
        verbose_name_plural = 'Inward Batch Lines'
        constraints = [
            models.UniqueConstraint(
                fields=['inward', 'item', 'batch_no'],
                name='unique_trn_inw_item_batch',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(mfg_dt__isnull=True)
                    | models.Q(exp_dt__isnull=True)
                    | models.Q(exp_dt__gt=models.F('mfg_dt'))
                ),
                name='trn_inw_dtl2_exp_after_mfg_when_both',
            ),
            models.CheckConstraint(
                condition=models.Q(batch_qty__gt=0),
                name='trn_inw_dtl2_batch_qty_positive',
            ),
        ]

    def __str__(self):
        return f"Inward {self.inward_id} item {self.item_id} batch {self.batch_no}"

    def clean(self):
        super().clean()
        if self.mfg_dt and self.exp_dt and self.exp_dt <= self.mfg_dt:
            raise ValidationError({'exp_dt': _('Expiry date must be after manufacturing date.')})
        if self.mfg_dt is None and self.exp_dt is not None:
            raise ValidationError({'mfg_dt': _('Manufacturing date is required when expiry date is set.')})

        if self.item_id and getattr(self.item, 'maintain_batch', None) != 'Y':
            raise ValidationError(
                _('Batch lines are only allowed when the item has Maintain Batches set to Yes.')
            )

        if self.inward_id and self.item_id:
            if not TrnInwDtl1.objects.filter(inward_id=self.inward_id, item_id=self.item_id).exists():
                raise ValidationError(
                    _('Each batch line must belong to an item line on the same inward.')
                )

        if self.batch_qty is not None and self.batch_qty <= 0:
            raise ValidationError({'batch_qty': _('Batch quantity must be greater than zero.')})

        if self.pack_style:
            self.pack_style = str(self.pack_style).strip()
            if not self.pack_style:
                raise ValidationError({'pack_style': _('Packing style is required.')})
            if len(self.pack_style) > 30:
                raise ValidationError({'pack_style': _('Packing style must be 30 characters or fewer.')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnSlsOrdHed(models.Model):
    """Sales order header (TrnSlsOrdHed)."""

    order_id = models.AutoField(primary_key=True)
    ord_rec_dt = models.DateField(verbose_name='Order record date')
    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='sales_orders',
        verbose_name='Customer',
    )
    cust_ord_id = models.CharField(max_length=20, verbose_name='Customer order ID')
    cust_ord_date = models.DateField(verbose_name='Customer order date')
    delivery_add = models.CharField(
        max_length=200, blank=True, null=True, verbose_name='Delivery address',
    )
    taxable_val = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Taxable value',
    )
    pkg_fwd_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Packing / forwarding amount',
    )
    frieght_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Freight amount',
    )
    oth_charges = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Other charges',
    )
    cgst_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='CGST amount',
    )
    sgst_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='SGST amount',
    )
    igst_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='IGST amount',
    )
    round_off = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, verbose_name='Round off',
    )
    total_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Total amount',
    )
    terms_cond = models.CharField(
        max_length=1000, blank=True, null=True, verbose_name='Terms and conditions',
    )
    remarks = models.CharField(
        max_length=500, blank=True, null=True, verbose_name='Remarks',
    )
    financial_year = models.ForeignKey(
        'masters.FinancialYear',
        on_delete=models.PROTECT,
        db_column='fy_id',
        related_name='sales_orders',
        verbose_name='Financial year',
        editable=False,
    )
    working_year = models.CharField(max_length=9, db_index=True, editable=False, verbose_name='Working year')
    document_path = models.CharField(
        max_length=150, blank=True, null=True, verbose_name='Document path',
    )

    class Meta:
        db_table = 'TrnSlsOrdHed'
        verbose_name = 'Sales order (header)'
        verbose_name_plural = 'Sales orders (headers)'
        ordering = ['-ord_rec_dt', '-order_id']
        constraints = [
            models.UniqueConstraint(fields=['customer', 'cust_ord_id'], name='unique_cust_custord_sales'),
            models.CheckConstraint(condition=models.Q(taxable_val__gte=0), name='trn_sls_hed_taxable_gte_0'),
            models.CheckConstraint(condition=models.Q(pkg_fwd_amt__gte=0), name='trn_sls_hed_pkg_fwd_gte_0'),
            models.CheckConstraint(condition=models.Q(frieght_amt__gte=0), name='trn_sls_hed_freight_gte_0'),
            models.CheckConstraint(condition=models.Q(oth_charges__gte=0), name='trn_sls_hed_oth_gte_0'),
            models.CheckConstraint(condition=models.Q(cgst_amt__gte=0), name='trn_sls_hed_cgst_gte_0'),
            models.CheckConstraint(condition=models.Q(sgst_amt__gte=0), name='trn_sls_hed_sgst_gte_0'),
            models.CheckConstraint(condition=models.Q(igst_amt__gte=0), name='trn_sls_hed_igst_gte_0'),
            models.CheckConstraint(condition=models.Q(total_amt__gte=0), name='trn_sls_hed_total_gte_0'),
            models.CheckConstraint(
                condition=models.Q(round_off__gte=-1) & models.Q(round_off__lte=1),
                name='trn_sls_hed_round_off_range',
            ),
            models.CheckConstraint(
                condition=models.Q(cust_ord_date__lte=models.F('ord_rec_dt')),
                name='trn_sls_hed_custord_dt_lte_ordrec',
            ),
        ]

    def __str__(self):
        return f'SO {self.order_id} — {self.cust_ord_id}'

    def clean(self):
        super().clean()
        if self.cust_ord_date and self.ord_rec_dt and self.cust_ord_date > self.ord_rec_dt:
            raise ValidationError({'cust_ord_date': _('Customer order date must not be after order record date.')})
        fy = getattr(self, 'financial_year', None)
        if fy and self.ord_rec_dt:
            if self.ord_rec_dt < fy.start_date or self.ord_rec_dt > fy.end_date:
                raise ValidationError({'ord_rec_dt': _('Order record date must fall within the financial year.')})
        if fy and self.cust_ord_date:
            if self.cust_ord_date < fy.start_date or self.cust_ord_date > fy.end_date:
                raise ValidationError({'cust_ord_date': _('Customer order date must fall within the financial year.')})

    def save(self, *args, **kwargs):
        if self.ord_rec_dt:
            fy = get_or_create_financial_year_for_date(self.ord_rec_dt)
            self.financial_year = fy
            self.working_year = fy.fy_display
        self.full_clean()
        super().save(*args, **kwargs)


class TrnSlsOrdDtl1(models.Model):
    """Sales order line (TrnSlsOrdDtl1)."""

    dtl1_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(
        TrnSlsOrdHed,
        on_delete=models.CASCADE,
        db_column='order_id',
        related_name='lines',
    )
    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        related_name='sales_order_lines',
    )
    hsn_no = models.CharField(max_length=50, verbose_name='HSN no.')
    packing_style = models.ForeignKey(
        'masters.MstPkgStyle',
        on_delete=models.PROTECT,
        db_column='pkg_style_id',
        related_name='sales_order_lines',
        verbose_name='Packing style',
    )
    order_qty = models.DecimalField(
        max_digits=10, decimal_places=SO_QTY_DECIMAL_PLACES, verbose_name='Order qty',
    )
    remaining_qty = models.DecimalField(
        max_digits=10,
        decimal_places=SO_QTY_DECIMAL_PLACES,
        default=0,
        verbose_name='Remaining qty',
        help_text='Remaining quantity to allocate (in Lakhs).',
    )
    is_completed = models.BooleanField(
        default=False,
        verbose_name='Completed',
        help_text='True when remaining qty reaches 0.',
    )
    is_sale_completed = models.BooleanField(
        default=False,
        verbose_name='Sale completed',
        help_text='True when all log-sheet batches for this line have been fully invoiced.',
    )
    ord_qty_nos = models.DecimalField(
        max_digits=12, decimal_places=0, default=0, verbose_name='Order qty (nos.)',
    )
    rate = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Rate')
    taxable_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Taxable amount',
    )
    gst_type = models.CharField(max_length=20, choices=GST_TYPE_CHOICES, verbose_name='GST type')
    gst_per = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='GST %')
    cgst_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='CGST amount')
    sgst_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='SGST amount')
    igst_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='IGST amount')
    prod_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Product amount')
    export_type = models.CharField(max_length=100, verbose_name='Export type')

    class Meta:
        db_table = 'TrnSlsOrdDtl1'
        verbose_name = 'Sales order line'
        verbose_name_plural = 'Sales order lines'
        ordering = ['dtl1_id']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'product', 'packing_style', 'rate'],
                name='unique_trn_sls_ord_line_triplet',
            ),
            models.CheckConstraint(condition=models.Q(order_qty__gt=0), name='trn_sls_dtl1_qty_positive'),
            models.CheckConstraint(condition=models.Q(rate__gt=0), name='trn_sls_dtl1_rate_positive'),
            models.CheckConstraint(condition=models.Q(taxable_amt__gte=0), name='trn_sls_dtl1_taxable_gte_0'),
            models.CheckConstraint(condition=models.Q(ord_qty_nos__gte=0), name='trn_sls_dtl1_ordnos_gte_0'),
            models.CheckConstraint(condition=models.Q(remaining_qty__gte=0), name='trn_sls_dtl1_remaining_gte_0'),
            models.CheckConstraint(condition=models.Q(gst_per__gte=0), name='trn_sls_dtl1_gstper_gte_0'),
            models.CheckConstraint(condition=models.Q(gst_per__lte=100), name='trn_sls_dtl1_gstper_lte_100'),
            models.CheckConstraint(
                condition=models.Q(gst_type__in=list(GST_TYPE_IDS)),
                name='trn_sls_dtl1_gst_type_enum',
            ),
        ]

    def __str__(self):
        return f'SO {self.order_id} prod {self.product_id}'

    def clean(self):
        super().clean()
        if self.product_id and self.packing_style_id and self.product and self.packing_style:
            if self.packing_style.pkg_type_id != self.product.prod_type_id:
                raise ValidationError(
                    {'packing_style': _('Packing style must belong to the product type of the selected product.')}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnSlsOrdDtl2(models.Model):
    """Sales order dispatch line (TrnSlsOrdDtl2)."""

    dtl2_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(
        TrnSlsOrdHed,
        on_delete=models.CASCADE,
        db_column='order_id',
        related_name='dispatch_lines',
    )
    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        related_name='sales_order_dispatches',
    )
    disp_sche_dt = models.DateField(verbose_name='Dispatch schedule date')
    disp_qty = models.DecimalField(
        max_digits=10, decimal_places=SO_QTY_DECIMAL_PLACES, verbose_name='Dispatch qty',
    )
    remarks = models.CharField(max_length=20, blank=True, null=True, verbose_name='Remarks')

    class Meta:
        db_table = 'TrnSlsOrdDtl2'
        verbose_name = 'Sales order dispatch'
        verbose_name_plural = 'Sales order dispatches'
        ordering = ['disp_sche_dt', 'dtl2_id']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'product', 'disp_sche_dt'],
                name='unique_trn_sls_ord_dispatch_dt',
            ),
            models.CheckConstraint(condition=models.Q(disp_qty__gt=0), name='trn_sls_dtl2_dispqty_positive'),
        ]

    def __str__(self):
        return f'SO {self.order_id} prod {self.product_id} @ {self.disp_sche_dt}'

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnBatchHed(models.Model):
    """
    Batch allocation header (TrnBatchHed) — one run of batch creation for an
    order line (customer + order + product).
    """

    batch_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='batch_headers',
        verbose_name='Customer',
    )
    order = models.ForeignKey(
        TrnSlsOrdHed,
        on_delete=models.CASCADE,
        db_column='order_id',
        related_name='batch_headers',
        verbose_name='Sales order',
    )
    order_line = models.ForeignKey(
        TrnSlsOrdDtl1,
        on_delete=models.CASCADE,
        db_column='order_dtl1_id',
        related_name='batch_headers',
        verbose_name='Sales order line',
        help_text='Specific sales order detail line this batch allocation belongs to.',
    )
    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        related_name='batch_headers',
        verbose_name='Product',
    )
    batch_size_l = models.DecimalField(
        max_digits=12,
        decimal_places=5,
        verbose_name='Batch size (Lacs)',
    )
    batch_size_n = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name='Batch size (Nos.)',
    )
    partial_yn = models.CharField(
        max_length=1,
        choices=[('Y', 'Yes'), ('N', 'No')],
        default='N',
        verbose_name='Partial allocation',
    )
    partial_qty_l = models.DecimalField(
        max_digits=12,
        decimal_places=5,
        blank=True,
        null=True,
        verbose_name='Partial qty (Lacs)',
    )
    partial_qty_n = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        blank=True,
        null=True,
        verbose_name='Partial qty (Nos.)',
    )
    batch_abbr = models.CharField(max_length=3, verbose_name='Batch abbreviation')
    batch_from = models.IntegerField(verbose_name='Batch range from')
    batch_to = models.IntegerField(verbose_name='Batch range to')

    class Meta:
        db_table = 'TrnBatchHed'
        verbose_name = 'Batch allocation (header)'
        verbose_name_plural = 'Batch allocation (headers)'
        ordering = ['-batch_id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(batch_from__lte=models.F('batch_to')),
                name='trn_batch_hed_from_lte_to',
            ),
            models.CheckConstraint(
                condition=models.Q(partial_yn__in=['Y', 'N']),
                name='trn_batch_hed_partial_yn_enum',
            ),
        ]

    def __str__(self):
        return f'Batch hed {self.batch_id} SO {self.order_id} prod {self.product_id}'


class TrnBatchDtl(models.Model):
    """Batch allocation line (TrnBatchDtl) — one physical batch number."""

    dtl_id = models.AutoField(primary_key=True)
    batch = models.ForeignKey(
        TrnBatchHed,
        on_delete=models.CASCADE,
        db_column='batch_id',
        related_name='lines',
        verbose_name='Batch header',
    )
    batch_no = models.CharField(
        max_length=15,
        unique=True,
        verbose_name='Batch no.',
    )
    batch_qty_l = models.DecimalField(
        max_digits=12,
        decimal_places=5,
        verbose_name='Batch qty (Lacs)',
    )
    batch_qty_n = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name='Batch qty (Nos.)',
    )
    mfg_dt = models.CharField(
        max_length=8,
        verbose_name='Mfg. (MMM-YYYY)',
        help_text='Manufacturing month, e.g. JAN-2026',
    )
    exp_dt = models.CharField(
        max_length=8,
        verbose_name='Exp. (MMM-YYYY)',
        help_text='Expiry month, e.g. DEC-2028',
    )
    log_sheet_flg = models.CharField(
        max_length=1,
        choices=[('Y', 'Yes'), ('N', 'No')],
        default='N',
        verbose_name='Log sheet',
    )

    class Meta:
        db_table = 'TrnBatchDtl'
        verbose_name = 'Batch allocation line'
        verbose_name_plural = 'Batch allocation lines'
        ordering = ['dtl_id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(log_sheet_flg__in=['Y', 'N']),
                name='trn_batch_dtl_logsheet_enum',
            ),
            models.CheckConstraint(
                condition=models.Q(batch_qty_l__gt=0),
                name='trn_batch_dtl_qty_l_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(batch_qty_n__gte=0),
                name='trn_batch_dtl_qty_n_gte_0',
            ),
        ]

    def __str__(self):
        return f'{self.batch_no} (hed {self.batch_id})'


LOGSHEET_SHIFT_DAY = 'Day'
LOGSHEET_SHIFT_NIGHT = 'Night'
LOGSHEET_SHIFT_CHOICES = [
    (LOGSHEET_SHIFT_DAY, LOGSHEET_SHIFT_DAY),
    (LOGSHEET_SHIFT_NIGHT, LOGSHEET_SHIFT_NIGHT),
]

# One log sheet row per batch line for single-layer; two rows (slots 1 and 2) for double-layer.
LOGSHEET_LAYER_SLOT_SINGLE = 'S'
LOGSHEET_LAYER_SLOT_FIRST = '1'
LOGSHEET_LAYER_SLOT_SECOND = '2'
LOGSHEET_LAYER_SLOT_CHOICES = [
    (LOGSHEET_LAYER_SLOT_SINGLE, 'Single layer'),
    (LOGSHEET_LAYER_SLOT_FIRST, 'First colour'),
    (LOGSHEET_LAYER_SLOT_SECOND, 'Second colour'),
]


def logsheet_split_batch_qty(batch_qty_n, batch_qty_l):
    """
    Split batch quantities across two double-layer runs.
    First colour gets floor (nos and lacs); second gets remainder so totals match the line.
    """
    n_raw = batch_qty_n
    if n_raw is None:
        n = 0
    else:
        n = int(n_raw) if not isinstance(n_raw, Decimal) else int(n_raw)
    n1 = n // 2
    n2 = n - n1
    l = batch_qty_l if batch_qty_l is not None else Decimal('0')
    if not isinstance(l, Decimal):
        l = Decimal(str(l))
    step = Decimal('1').scaleb(-5)
    l1 = (l / Decimal('2')).quantize(step, rounding=ROUND_FLOOR)
    l2 = (l - l1).quantize(step)
    return n1, n2, l1, l2


class TrnLogSheet(models.Model):
    """
    Granulation log sheet (Trn_LogSheet).

    batch_id references one physical batch line (TrnBatchDtl.dtl_id) from batch allocation.
    """

    logsheet_id = models.AutoField(primary_key=True)
    section = models.ForeignKey(
        'masters.MstSection',
        on_delete=models.PROTECT,
        db_column='section_id',
        related_name='log_sheets',
        verbose_name='Section',
    )
    gran_dt = models.DateField(verbose_name='Granulation date')
    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='log_sheets',
        verbose_name='Customer',
    )
    shift_id = models.CharField(
        max_length=5,
        db_column='shift_id',
        choices=LOGSHEET_SHIFT_CHOICES,
        verbose_name='Shift',
    )
    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        related_name='log_sheets',
        verbose_name='Product',
    )
    batch_line = models.ForeignKey(
        TrnBatchDtl,
        on_delete=models.PROTECT,
        db_column='batch_id',
        related_name='log_sheets',
        verbose_name='Batch allocation line',
    )
    blend_dt = models.DateField(
        blank=True,
        null=True,
        verbose_name='Blending date',
    )
    dpr_flg = models.CharField(
        max_length=1,
        choices=[('Y', 'Yes'), ('N', 'No')],
        default='N',
        verbose_name='DPR flag',
    )
    rm_disp_flg = models.CharField(
        max_length=1,
        choices=[('Y', 'Yes'), ('N', 'No')],
        default='N',
        verbose_name='RM dispensing completed',
        help_text='Y when all BOM stages have at least one RM dispensing record for this log sheet/spec.',
    )
    layer_slot = models.CharField(
        max_length=1,
        choices=LOGSHEET_LAYER_SLOT_CHOICES,
        default=LOGSHEET_LAYER_SLOT_SINGLE,
        verbose_name='Layer / colour slot',
        help_text='S = single-layer batch; 1 / 2 = first or second colour for double-layer.',
    )

    class Meta:
        db_table = 'Trn_LogSheet'
        verbose_name = 'Log sheet'
        verbose_name_plural = 'Log sheets'
        ordering = ['-gran_dt', '-logsheet_id']
        constraints = [
            models.UniqueConstraint(
                fields=['batch_line', 'layer_slot'],
                name='unique_trn_logsheet_batch_layer_slot',
            ),
            models.CheckConstraint(
                condition=models.Q(shift_id__in=[LOGSHEET_SHIFT_DAY, LOGSHEET_SHIFT_NIGHT]),
                name='trn_logsheet_shift_enum',
            ),
            models.CheckConstraint(
                condition=models.Q(dpr_flg__in=['Y', 'N']),
                name='trn_logsheet_dpr_enum',
            ),
            models.CheckConstraint(
                condition=models.Q(rm_disp_flg__in=['Y', 'N']),
                name='trn_logsheet_rm_disp_enum',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    layer_slot__in=[
                        LOGSHEET_LAYER_SLOT_SINGLE,
                        LOGSHEET_LAYER_SLOT_FIRST,
                        LOGSHEET_LAYER_SLOT_SECOND,
                    ]
                ),
                name='trn_logsheet_layer_slot_enum',
            ),
        ]

    def __str__(self):
        return f'LogSheet {self.logsheet_id} — {self.batch_line_id} @ {self.gran_dt}'

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        from masters.models import MstProd

        if self.batch_line_id and self.product_id and self.customer_id:
            bl = self.batch_line
            if bl.batch.product_id != self.product_id:
                raise ValidationError({'product': _('Product must match the selected batch allocation line.')})
            if bl.batch.customer_id != self.customer_id:
                raise ValidationError({'customer': _('Customer must match the selected batch allocation line.')})
            slot = (self.layer_slot or LOGSHEET_LAYER_SLOT_SINGLE).strip()
            pl = bl.batch.product.tablet_layer
            if pl == MstProd.LAYER_SINGLE:
                if slot != LOGSHEET_LAYER_SLOT_SINGLE:
                    raise ValidationError(
                        {'layer_slot': _('Single-layer products must use the single log sheet slot.')}
                    )
            elif pl == MstProd.LAYER_DOUBLE:
                if slot not in (LOGSHEET_LAYER_SLOT_FIRST, LOGSHEET_LAYER_SLOT_SECOND):
                    raise ValidationError(
                        {'layer_slot': _('Double-layer batches require first or second colour slot.')}
                    )
            mfg = (bl.mfg_dt or '').strip().upper()
            exp = (bl.exp_dt or '').strip().upper()
            if mfg and exp:
                try:
                    y1, m1, _ = _logsheet_parse_mmm_yyyy(mfg, 'MFG')
                    y2, m2, _ = _logsheet_parse_mmm_yyyy(exp, 'EXP')
                except ValidationError:
                    raise
                if _logsheet_ym_key(y2, m2) <= _logsheet_ym_key(y1, m1):
                    raise ValidationError(
                        _('Manufacturing period must be before expiry period for this batch.')
                    )


def _logsheet_parse_mmm_yyyy(raw, label):
    s = (raw or '').strip().upper()
    m = re.match(
        r'^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{4})$',
        s,
    )
    if not m:
        raise ValidationError(_('%(label)s date must be in MMM-YYYY format.') % {'label': label})
    mon_abbr = m.group(1)
    month = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
    }.get(mon_abbr)
    if not month:
        raise ValidationError(_('Invalid month in batch dates.'))
    year = int(m.group(2))
    return year, month, s


def _logsheet_ym_key(year, month):
    return year * 100 + month


# Daily Production Report (DPR) — shifts include General per business spec.
DPR_SHIFT_GENERAL = 'General'
DPR_SHIFT_CHOICES = [
    (LOGSHEET_SHIFT_DAY, LOGSHEET_SHIFT_DAY),
    (LOGSHEET_SHIFT_NIGHT, LOGSHEET_SHIFT_NIGHT),
    (DPR_SHIFT_GENERAL, DPR_SHIFT_GENERAL),
]

DPR_MACHINE_WORKING = 'working'
DPR_MACHINE_NOT_WORKING = 'not_working'
DPR_MACHINE_STATUS_CHOICES = [
    (DPR_MACHINE_WORKING, 'Working'),
    (DPR_MACHINE_NOT_WORKING, 'Not working'),
]


class TrnDpr(models.Model):
    """
    Daily production report (TrnDPR).

    batch_line + log_sheet reference one log sheet row (batch allocation line with an existing log sheet).
    """

    trn_dpr_id = models.AutoField(primary_key=True, db_column='TrnDpr_id')
    trn_dpr_dt = models.DateField(db_column='TrnDpr_dt', verbose_name='DPR date')

    section = models.ForeignKey(
        'masters.MstSection',
        on_delete=models.PROTECT,
        db_column='Section_id',
        related_name='dpr_entries',
        verbose_name='Section',
    )
    machine = models.ForeignKey(
        'masters.MstMachine',
        on_delete=models.PROTECT,
        db_column='Machine_id',
        related_name='dpr_entries',
        verbose_name='Machine',
    )
    shift_id = models.CharField(
        max_length=10,
        db_column='Shift_id',
        choices=DPR_SHIFT_CHOICES,
        verbose_name='Shift',
    )
    machine_working = models.CharField(
        max_length=20,
        db_column='Machine_working',
        choices=DPR_MACHINE_STATUS_CHOICES,
        default=DPR_MACHINE_WORKING,
        verbose_name='Machine status',
    )

    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='Cust_id',
        related_name='dpr_entries',
        verbose_name='Customer',
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='Prod_id',
        related_name='dpr_entries',
        verbose_name='Product',
        null=True,
        blank=True,
    )
    batch_line = models.ForeignKey(
        TrnBatchDtl,
        on_delete=models.PROTECT,
        db_column='TrnBatch_id',
        related_name='dpr_entries',
        verbose_name='Batch allocation line',
        null=True,
        blank=True,
    )
    log_sheet = models.ForeignKey(
        TrnLogSheet,
        on_delete=models.PROTECT,
        db_column='LogSheet_id',
        related_name='dpr_entries',
        verbose_name='Log sheet',
        null=True,
        blank=True,
    )
    specification = models.ForeignKey(
        'masters.MstBomRmHed',
        on_delete=models.PROTECT,
        db_column='Spec_id',
        related_name='dpr_entries',
        verbose_name='Specification',
        null=True,
        blank=True,
    )

    batch_rem = models.CharField(
        max_length=30,
        blank=True,
        default='',
        db_column='Batch_rem',
        verbose_name='Batch remarks',
    )
    lot_no = models.PositiveSmallIntegerField(db_column='Lot_no', verbose_name='Lot nos.')
    qty_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        db_column='Qty_kg',
        verbose_name='Qty (kg)',
        default=0,
    )
    qty_nos = models.PositiveBigIntegerField(
        db_column='Qty_nos',
        verbose_name='Qty (nos.)',
        default=0,
    )
    section_qty = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
        db_column='Section_qty',
        verbose_name='Section qty',
    )
    batch_size_lakh = models.DecimalField(
        max_digits=12,
        decimal_places=5,
        blank=True,
        null=True,
        db_column='Batch_size_lakh',
        verbose_name='Batch size (Lakh)',
        help_text='Granulation / lubrication multi-batch DPR: manual batch size in lac.',
    )

    start_time = models.TimeField(db_column='Start_time', verbose_name='Start time')
    end_time = models.TimeField(db_column='End_time', verbose_name='End time')
    total_time = models.CharField(
        max_length=24,
        blank=True,
        default='',
        db_column='Total_time',
        verbose_name='Total time',
    )

    operator1 = models.ForeignKey(
        'masters.MstOperator',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='Operator1_id',
        related_name='dpr_entries_primary',
        verbose_name='Operator (1)',
    )
    operator2 = models.ForeignKey(
        'masters.MstOperator',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='Operator2_id',
        related_name='dpr_entries_secondary',
        verbose_name='Operator (2)',
    )
    operators = models.ManyToManyField(
        'masters.MstOperator',
        blank=True,
        related_name='dpr_entries',
        verbose_name='Operators',
    )
    no_of_helper = models.PositiveSmallIntegerField(
        db_column='No_of_Helper',
        default=0,
        verbose_name='No. of helpers',
    )
    remarks = models.CharField(
        max_length=500,
        blank=True,
        default='',
        db_column='Remarks',
        verbose_name='Remarks',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_column='Created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='Updated_at')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='Created_by_id',
        related_name='dpr_entries_created',
        verbose_name='Created by',
    )
    # MySQL cannot enforce partial unique indexes; this mirrors the old partial unique on
    # (batch_line, log_sheet, machine, shift_id, section, trn_dpr_dt) when batch_line is set.
    dpr_batch_scope_key = models.CharField(
        max_length=220,
        null=True,
        blank=True,
        unique=True,
        db_column='Dpr_batch_scope_key',
        editable=False,
        verbose_name='Batch scope key',
    )

    class Meta:
        db_table = 'TrnDPR'
        verbose_name = 'Daily production report'
        verbose_name_plural = 'Daily production reports'
        ordering = ['-trn_dpr_dt', '-trn_dpr_id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(shift_id__in=[LOGSHEET_SHIFT_DAY, LOGSHEET_SHIFT_NIGHT, DPR_SHIFT_GENERAL]),
                name='trn_dpr_shift_enum',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    machine_working__in=[DPR_MACHINE_WORKING, DPR_MACHINE_NOT_WORKING]
                ),
                name='trn_dpr_machine_working_enum',
            ),
            models.CheckConstraint(
                condition=models.Q(no_of_helper__lte=999),
                name='trn_dpr_helpers_max',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(batch_line__isnull=True, log_sheet__isnull=True)
                    | models.Q(batch_line__isnull=False, log_sheet__isnull=False)
                ),
                name='trn_dpr_batch_logsheet_both_or_neither',
            ),
        ]

    def __str__(self):
        return f'DPR {self.trn_dpr_id} @ {self.trn_dpr_dt}'

    @staticmethod
    def build_batch_scope_key(batch_line_id, log_sheet_id, machine_id, shift_id, section_id, trn_dpr_dt):
        return (
            f'{batch_line_id}:{log_sheet_id}:{machine_id}:'
            f'{shift_id}:{section_id}:{trn_dpr_dt.isoformat()}'
        )

    def clean(self):
        super().clean()
        if self.batch_line_id and self.log_sheet_id:
            self.dpr_batch_scope_key = self.build_batch_scope_key(
                self.batch_line_id,
                self.log_sheet_id,
                self.machine_id,
                self.shift_id,
                self.section_id,
                self.trn_dpr_dt,
            )
        else:
            self.dpr_batch_scope_key = None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        if self.machine_working == DPR_MACHINE_WORKING and self.log_sheet_id is not None:
            TrnLogSheet.objects.filter(pk=self.log_sheet_id).update(dpr_flg='Y')


class TrnDprInputBatch(models.Model):
    """
    Links a DPR row to one log sheet row (granulation / lubrication multi-select).

    One row per colour slot when applicable. ``TrnDpr.batch_line`` / ``TrnDpr.log_sheet`` stay null.
    """

    input_id = models.AutoField(primary_key=True, db_column='TrnDprInputBatch_id')
    dpr = models.ForeignKey(
        'TrnDpr',
        on_delete=models.CASCADE,
        db_column='TrnDpr_id',
        related_name='input_batches',
        verbose_name='DPR',
    )
    log_sheet = models.ForeignKey(
        TrnLogSheet,
        on_delete=models.PROTECT,
        db_column='LogSheet_id',
        related_name='dpr_input_links',
        verbose_name='Log sheet',
    )

    class Meta:
        db_table = 'TrnDPRInputBatch'
        verbose_name = 'DPR input batch'
        verbose_name_plural = 'DPR input batches'
        ordering = ['input_id']
        constraints = [
            models.UniqueConstraint(
                fields=['dpr', 'log_sheet'],
                name='unique_dpr_input_log_sheet',
            ),
        ]

    def __str__(self):
        return f'DPR {self.dpr_id} ← log sheet {self.log_sheet_id}'


class TrnlssHed(models.Model):
    """Raw material dispensing header (TrnlssHed)."""

    dispensing_id = models.AutoField(primary_key=True, db_column='Dispensing_Id')
    dispensing_dt = models.DateField(db_column='Dispensing_dt', verbose_name='Dispensing date')

    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='Cust_id',
        related_name='rm_dispensings',
        verbose_name='Customer',
    )
    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='Prod_id',
        related_name='rm_dispensings',
        verbose_name='Product',
    )
    batch_line = models.ForeignKey(
        TrnLogSheet,
        on_delete=models.PROTECT,
        db_column='Batch_id',
        related_name='rm_dispensings',
        verbose_name='Log sheet',
    )
    specification = models.ForeignKey(
        'masters.MstBomRmHed',
        on_delete=models.PROTECT,
        db_column='Spec_id',
        related_name='rm_dispensings',
        verbose_name='Specification',
    )
    machine = models.ForeignKey(
        'masters.MstMachine',
        on_delete=models.PROTECT,
        db_column='Machine_id',
        related_name='rm_dispensings',
        verbose_name='Machine',
    )

    lot_no = models.PositiveIntegerField(db_column='Lot_no', verbose_name='No. of lots')

    dispensed_by = models.CharField(max_length=150, db_column='Dispensed_by', verbose_name='Dispensed by')
    worker_name = models.CharField(max_length=150, db_column='Worker_name', verbose_name='Worker name')
    checked_by = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_column='Checked_by',
        verbose_name='Checked by',
    )
    verified_by = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_column='Verified_by',
        verbose_name='Verified by',
    )
    remarks = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_column='Remarks',
        verbose_name='Remarks',
    )

    class Meta:
        db_table = 'TrnlssHed'
        verbose_name = 'RM dispensing (header)'
        verbose_name_plural = 'RM dispensings (headers)'
        ordering = ['-dispensing_dt', '-dispensing_id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(lot_no__gt=0),
                name='trnlss_hed_lot_no_positive',
            ),
        ]

    def __str__(self):
        return f'RM Dispensing {self.dispensing_id} — {self.dispensing_dt}'

    def clean(self):
        super().clean()
        if self.batch_line_id and self.customer_id and self.batch_line:
            if self.batch_line.customer_id != self.customer_id:
                raise ValidationError({'customer': _('Customer must match the selected log sheet.')})
        if self.batch_line_id and self.product_id and self.batch_line:
            if self.batch_line.product_id != self.product_id:
                raise ValidationError({'product': _('Product must match the selected log sheet.')})
        if self.specification_id and self.customer_id and self.specification:
            if self.specification.customer_id != self.customer_id:
                raise ValidationError({'specification': _('Specification must belong to the selected customer.')})
        if self.specification_id and self.product_id and self.specification:
            if self.specification.product_id != self.product_id:
                raise ValidationError({'specification': _('Specification must belong to the selected product.')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnlssDtl(models.Model):
    """Raw material dispensing detail (TrnlssDtl)."""

    dtl_id = models.AutoField(primary_key=True)
    dispensing = models.ForeignKey(
        TrnlssHed,
        on_delete=models.CASCADE,
        db_column='Dispensing_Id',
        related_name='lines',
        verbose_name='Dispensing',
    )
    stage = models.ForeignKey(
        'masters.MstPdnStage',
        on_delete=models.PROTECT,
        db_column='Stage_id',
        related_name='rm_dispensing_lines',
        verbose_name='Production stage',
    )
    item = models.ForeignKey(
        'masters.MstItem',
        on_delete=models.PROTECT,
        db_column='Item_id',
        related_name='rm_dispensing_lines',
        verbose_name='Item',
    )
    qty_per_lakh = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        db_column='Qty_PerLack',
        verbose_name='Qty per lakh',
    )
    issue_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        db_column='Issue_qty',
        verbose_name='Dispensing qty',
    )
    issue_add_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        db_column='Issue_AddQty',
        verbose_name='Additional qty',
        default=0,
    )
    issue_date = models.DateField(db_column='Issue_date', verbose_name='Dispensing date')
    remarks = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        db_column='Remarks',
        verbose_name='Remarks',
    )

    class Meta:
        db_table = 'TrnlssDtl'
        verbose_name = 'RM dispensing (line)'
        verbose_name_plural = 'RM dispensing (lines)'
        ordering = ['dtl_id']
        constraints = [
            models.UniqueConstraint(
                fields=['dispensing', 'stage', 'item'],
                name='unique_trnlss_stage_item_per_dispensing',
            ),
            models.CheckConstraint(
                condition=models.Q(qty_per_lakh__gte=0),
                name='trnlss_dtl_qty_per_lakh_gte_0',
            ),
            models.CheckConstraint(
                condition=models.Q(issue_qty__gte=0),
                name='trnlss_dtl_issue_qty_gte_0',
            ),
            models.CheckConstraint(
                condition=models.Q(issue_add_qty__gte=0),
                name='trnlss_dtl_issue_add_qty_gte_0',
            ),
        ]

    def __str__(self):
        return f'Disp {self.dispensing_id} stage {self.stage_id} item {self.item_id}'

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnPkgCont(models.Model):
    """
    Daily packing (contractors) — TrnPkgCont.

    Product and physical batch are implied by ``log_sheet`` (no duplicate product/batch columns).
    """

    pkgcont_id = models.AutoField(primary_key=True, db_column='PkgCont_id')
    pkgcont_date = models.DateField(db_column='PkgCont_Date', verbose_name='Packing date')

    contractor = models.ForeignKey(
        'masters.MstOperator',
        on_delete=models.PROTECT,
        db_column='Contractor_id',
        related_name='packing_contractor_entries',
        verbose_name='Contractor',
    )
    no_of_girls = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        db_column='No_of_Girls',
        verbose_name='No. of girls',
        help_text='Packing manpower (optional).',
    )

    log_sheet = models.ForeignKey(
        TrnLogSheet,
        on_delete=models.PROTECT,
        db_column='LogSheet_id',
        related_name='packing_contractor_entries',
        verbose_name='Log sheet (batch)',
    )
    pkg_style = models.ForeignKey(
        'masters.MstPkgStyle',
        on_delete=models.PROTECT,
        db_column='PkgStyle_id',
        related_name='packing_contractor_entries',
        verbose_name='Packing style',
    )

    shipper_no = models.PositiveIntegerField(
        db_column='Shipper_no',
        verbose_name='Shipper no.',
        help_text='Number of shippers / cartons (1–999999).',
    )
    qty_nos = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        db_column='Qty_nos',
        verbose_name='Qty (nos.)',
    )
    qty_loose = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        blank=True,
        null=True,
        db_column='Qty_loose',
        verbose_name='Qty (loose)',
    )
    remarks = models.TextField(blank=True, null=True, db_column='Remarks', verbose_name='Remarks')

    class Meta:
        db_table = 'TrnPkgCont'
        verbose_name = 'Daily packing (contractor)'
        verbose_name_plural = 'Daily packing (contractors)'
        ordering = ['-pkgcont_date', '-pkgcont_id']
        constraints = [
            models.UniqueConstraint(
                fields=['pkgcont_date', 'log_sheet', 'contractor', 'pkg_style'],
                name='unique_pkgcont_date_logsheet_contractor_style',
            ),
            models.CheckConstraint(
                condition=models.Q(shipper_no__gte=1) & models.Q(shipper_no__lte=999999),
                name='trn_pkgcont_shipper_range',
            ),
            models.CheckConstraint(
                condition=models.Q(qty_nos__gte=1),
                name='trn_pkgcont_qty_nos_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(no_of_girls__isnull=True) | models.Q(no_of_girls__lte=9999),
                name='trn_pkgcont_girls_max',
            ),
            models.CheckConstraint(
                condition=models.Q(qty_loose__isnull=True) | models.Q(qty_loose__gte=0),
                name='trn_pkgcont_qty_loose_gte_0',
            ),
        ]

    def __str__(self):
        return f'PkgCont {self.pkgcont_id} @ {self.pkgcont_date}'

    def clean(self):
        super().clean()
        if self.contractor_id and self.contractor:
            des = (self.contractor.designation or '').strip()
            if des.upper() != 'CONTRACTOR':
                raise ValidationError({'contractor': _('Selected operator must have designation Contractor.')})
        if self.log_sheet_id and self.pkg_style_id and self.log_sheet and self.pkg_style:
            prod = self.log_sheet.product
            if prod and self.pkg_style.pkg_type_id != prod.prod_type_id:
                raise ValidationError(
                    {'pkg_style': _('Packing style must belong to the product type of the log sheet product.')}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnSlsHed(models.Model):
    """Sales invoice header (TrnSlsHed)."""

    invoice_id = models.AutoField(primary_key=True)
    invoice_no = models.CharField(
        max_length=15,
        verbose_name='Invoice no.',
        help_text='Format: SI- plus digits (per financial year sequence).',
        validators=[
            RegexValidator(
                INVOICE_NO_PATTERN,
                _('Must match SI- plus digits (e.g. SI-00001).'),
            ),
        ],
    )
    invoice_dt = models.DateField(verbose_name='Invoice date')

    financial_year = models.ForeignKey(
        'masters.FinancialYear',
        on_delete=models.PROTECT,
        db_column='fy_id',
        related_name='sales_invoices',
        verbose_name='Financial year',
        editable=False,
    )
    working_year = models.CharField(
        max_length=9,
        db_index=True,
        editable=False,
        verbose_name='Working year',
    )

    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='sales_invoices',
        verbose_name='Customer',
    )
    transporter = models.ForeignKey(
        'masters.MstTransport',
        on_delete=models.PROTECT,
        db_column='transport_id',
        related_name='sales_invoices',
        verbose_name='Transporter',
    )
    reference_order = models.ForeignKey(
        'TrnSlsOrdHed',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='ref_order_id',
        related_name='invoices_as_reference',
        verbose_name='Reference sales order',
    )

    delivery_add = models.TextField(verbose_name='Delivery address')

    taxable_val = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Taxable value',
    )
    pkg_fwd_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Packing / forwarding amount',
    )
    freight_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Freight amount',
    )
    oth_charges = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Other charges',
    )
    cgst_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='CGST amount',
    )
    sgst_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='SGST amount',
    )
    igst_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='IGST amount',
    )
    round_off = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, verbose_name='Round off',
    )
    total_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Total amount',
    )
    remarks = models.TextField(blank=True, null=True, verbose_name='Remarks')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='created_by_id',
        related_name='sales_invoices_created',
        verbose_name='Created by',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='updated_by_id',
        related_name='sales_invoices_updated',
        verbose_name='Updated by',
    )

    class Meta:
        db_table = 'TrnSlsHed'
        verbose_name = 'Sales invoice (header)'
        verbose_name_plural = 'Sales invoices (headers)'
        ordering = ['-invoice_dt', '-invoice_id']
        constraints = [
            models.UniqueConstraint(
                fields=['invoice_no', 'financial_year'],
                name='unique_sales_invoice_no_per_fy',
            ),
            models.CheckConstraint(condition=models.Q(taxable_val__gte=0), name='trn_sls_inv_hed_taxable_gte_0'),
            models.CheckConstraint(condition=models.Q(pkg_fwd_amt__gte=0), name='trn_sls_inv_hed_pkg_fwd_gte_0'),
            models.CheckConstraint(condition=models.Q(freight_amt__gte=0), name='trn_sls_inv_hed_freight_gte_0'),
            models.CheckConstraint(condition=models.Q(oth_charges__gte=0), name='trn_sls_inv_hed_oth_gte_0'),
            models.CheckConstraint(condition=models.Q(cgst_amt__gte=0), name='trn_sls_inv_hed_cgst_gte_0'),
            models.CheckConstraint(condition=models.Q(sgst_amt__gte=0), name='trn_sls_inv_hed_sgst_gte_0'),
            models.CheckConstraint(condition=models.Q(igst_amt__gte=0), name='trn_sls_inv_hed_igst_gte_0'),
            models.CheckConstraint(condition=models.Q(total_amt__gte=0), name='trn_sls_inv_hed_total_gte_0'),
            models.CheckConstraint(
                condition=models.Q(round_off__gte=-1) & models.Q(round_off__lte=1),
                name='trn_sls_inv_hed_round_off_range',
            ),
        ]

    def __str__(self):
        return f'Invoice {self.invoice_no}'

    def clean(self):
        super().clean()
        if self.invoice_no:
            self.invoice_no = self.invoice_no.strip().upper()
            if not re.fullmatch(INVOICE_NO_PATTERN, self.invoice_no):
                raise ValidationError({'invoice_no': _('Must match SI- plus digits (e.g. SI-00001).')})
        fy = getattr(self, 'financial_year', None)
        if fy and self.invoice_dt:
            if self.invoice_dt < fy.start_date or self.invoice_dt > fy.end_date:
                raise ValidationError({'invoice_dt': _('Invoice date must fall within the financial year.')})

    def save(self, *args, **kwargs):
        if self.invoice_dt:
            fy = get_or_create_financial_year_for_date(self.invoice_dt)
            self.financial_year = fy
            self.working_year = fy.fy_display
        self.full_clean()
        super().save(*args, **kwargs)


class TrnSlsDtl1(models.Model):
    """Sales invoice product line (TrnSlsDtl1)."""

    dtl1_id = models.AutoField(primary_key=True)
    invoice = models.ForeignKey(
        TrnSlsHed,
        on_delete=models.CASCADE,
        db_column='invoice_id',
        related_name='lines',
    )
    order_line = models.ForeignKey(
        TrnSlsOrdDtl1,
        on_delete=models.PROTECT,
        db_column='order_dtl1_id',
        related_name='sales_invoice_lines',
        verbose_name='Sales order line',
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        related_name='sales_invoice_lines',
        verbose_name='Product',
    )
    packing_style = models.ForeignKey(
        'masters.MstPkgStyle',
        on_delete=models.PROTECT,
        db_column='pkg_style_id',
        related_name='sales_invoice_lines',
        verbose_name='Packing style',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=QTY_DECIMAL_PLACES,
        verbose_name='Quantity (lac)',
    )
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name='Rate',
    )
    taxable_amt = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Taxable amount',
    )
    gst_type = models.CharField(max_length=20, choices=GST_TYPE_CHOICES, verbose_name='GST type')
    gst_per = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='GST %')
    cgst_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='CGST amount')
    sgst_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='SGST amount')
    igst_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='IGST amount')
    prod_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Product amount')

    class Meta:
        db_table = 'TrnSlsDtl1'
        verbose_name = 'Sales invoice line'
        verbose_name_plural = 'Sales invoice lines'
        ordering = ['dtl1_id']
        constraints = [
            models.UniqueConstraint(
                fields=['invoice', 'order_line'],
                condition=models.Q(order_line__isnull=False),
                name='uniq_trn_sls_inv_dtl1_inv_ordline',
            ),
            models.UniqueConstraint(
                fields=['invoice', 'product', 'packing_style'],
                condition=models.Q(order_line__isnull=True),
                name='uniq_trn_sls_inv_dtl1_inv_prod_pkg',
            ),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='trn_sls_inv_dtl1_qty_positive'),
            models.CheckConstraint(condition=models.Q(rate__gt=0), name='trn_sls_inv_dtl1_rate_positive'),
            models.CheckConstraint(condition=models.Q(taxable_amt__gte=0), name='trn_sls_inv_dtl1_taxable_gte_0'),
            models.CheckConstraint(condition=models.Q(gst_per__gte=0), name='trn_sls_inv_dtl1_gstper_gte_0'),
            models.CheckConstraint(condition=models.Q(gst_per__lte=100), name='trn_sls_inv_dtl1_gstper_lte_100'),
            models.CheckConstraint(
                condition=models.Q(gst_type__in=list(GST_TYPE_IDS)),
                name='trn_sls_inv_dtl1_gst_type_enum',
            ),
        ]

    def __str__(self):
        return f'Inv {self.invoice_id} prod {self.product_id}'

    def clean(self):
        super().clean()
        if self.product_id and self.packing_style_id and self.product and self.packing_style:
            if self.packing_style.pkg_type_id != self.product.prod_type_id:
                raise ValidationError(
                    {'packing_style': _('Packing style must belong to the product type of the selected product.')}
                )
        if self.order_line_id and self.order_line and self.invoice_id:
            ol = self.order_line
            if ol.product_id != self.product_id:
                raise ValidationError({'product': _('Product must match the linked sales order line.')})
            if ol.packing_style_id != self.packing_style_id:
                raise ValidationError(
                    {'packing_style': _('Packing style must match the linked sales order line.')}
                )
            inv = self.invoice
            if inv and inv.customer_id and ol.order.customer_id != inv.customer_id:
                raise ValidationError(_('Sales order line must belong to the same customer as the invoice.'))

        gt = (self.gst_type or '').strip()
        cg = self.cgst_amt or Decimal('0')
        sg = self.sgst_amt or Decimal('0')
        ig = self.igst_amt or Decimal('0')
        if gt == GST_TYPE_IGST:
            if cg != 0 or sg != 0:
                raise ValidationError(_('IGST lines must not carry CGST or SGST amounts.'))
        elif gt == GST_TYPE_CGST_SGST:
            if ig != 0:
                raise ValidationError(_('CGST+SGST lines must not carry IGST amount.'))
        elif gt == GST_TYPE_EXEMPTED:
            if cg != 0 or sg != 0 or ig != 0:
                raise ValidationError(_('Exempted lines must have zero GST amounts.'))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrnSlsDtl2(models.Model):
    """Sales invoice batch allocation (TrnSlsDtl2) — links to granulation log sheet row."""

    dtl2_id = models.AutoField(primary_key=True)
    invoice_line = models.ForeignKey(
        TrnSlsDtl1,
        on_delete=models.CASCADE,
        db_column='invoice_dtl1_id',
        related_name='batch_lines',
        verbose_name='Invoice line',
    )
    log_sheet = models.ForeignKey(
        TrnLogSheet,
        on_delete=models.PROTECT,
        db_column='logsheet_id',
        related_name='sales_invoice_batches',
        verbose_name='Log sheet',
    )
    batch_qty = models.DecimalField(
        max_digits=14,
        decimal_places=QTY_DECIMAL_PLACES,
        verbose_name='Batch qty (lac)',
    )

    class Meta:
        db_table = 'TrnSlsDtl2'
        verbose_name = 'Sales invoice batch line'
        verbose_name_plural = 'Sales invoice batch lines'
        ordering = ['dtl2_id']
        constraints = [
            models.UniqueConstraint(
                fields=['invoice_line', 'log_sheet'],
                name='uniq_trn_sls_inv_dtl2_line_logsheet',
            ),
            models.CheckConstraint(condition=models.Q(batch_qty__gt=0), name='trn_sls_inv_dtl2_batch_qty_positive'),
        ]

    def __str__(self):
        return f'Inv line {self.invoice_line_id} log {self.log_sheet_id}'

    def clean(self):
        super().clean()
        if self.invoice_line_id and self.log_sheet_id and self.invoice_line and self.log_sheet:
            ls = self.log_sheet
            ln = self.invoice_line
            if ls.product_id != ln.product_id:
                raise ValidationError({'log_sheet': _('Log sheet product must match the invoice line product.')})
            inv = ln.invoice
            if inv and ls.customer_id != inv.customer_id:
                raise ValidationError({'log_sheet': _('Log sheet customer must match the invoice customer.')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
