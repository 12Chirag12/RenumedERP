"""
Inventory app models: monthly snapshot table (legacy / admin), centralized
``InventoryStock`` ledger, and stock adjustment documents.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from transactions.constants import QTY_DECIMAL_PLACES, SO_QTY_DECIMAL_PLACES


class InvCustMonthlyStock(models.Model):
    """
    One row per customer product per calendar month (opening / receipt / issue in lakhs).

    No longer edited from the main app UI; rows remain available in Django admin.
    Operational batch balances live in ``InventoryStock``.
    """

    inv_mth_id = models.AutoField(primary_key=True)

    cust_product = models.ForeignKey(
        'masters.MstCustProd',
        on_delete=models.CASCADE,
        db_column='cust_prod_id',
        related_name='monthly_inventory_rows',
        verbose_name='Customer product',
    )

    year = models.PositiveSmallIntegerField(verbose_name='Year')
    month = models.PositiveSmallIntegerField(verbose_name='Month')

    opening_qty_lac = models.DecimalField(
        max_digits=12,
        decimal_places=SO_QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        verbose_name='Opening qty (lac)',
    )

    receipt_qty_lac = models.DecimalField(
        max_digits=12,
        decimal_places=SO_QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        verbose_name='Received / supplied (lac)',
        help_text='Stock moved to the customer during this month.',
    )

    issue_qty_lac = models.DecimalField(
        max_digits=12,
        decimal_places=SO_QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        verbose_name='Issued / consumed (lac)',
        help_text='Stock removed from the customer balance during this month.',
    )

    remarks = models.CharField(max_length=300, blank=True, verbose_name='Remarks')

    class Meta:
        db_table = 'InvCustMonthlyStock'
        verbose_name = 'Customer monthly inventory'
        verbose_name_plural = 'Customer monthly inventory'
        ordering = ['year', 'month', 'cust_product__customer', 'cust_product__product']
        constraints = [
            models.UniqueConstraint(
                fields=['cust_product', 'year', 'month'],
                name='unique_inv_cust_prod_month',
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name='inv_cust_mth_month_range',
            ),
            models.CheckConstraint(
                condition=models.Q(opening_qty_lac__gte=0),
                name='inv_cust_mth_opening_gte_0',
            ),
            models.CheckConstraint(
                condition=models.Q(receipt_qty_lac__gte=0),
                name='inv_cust_mth_receipt_gte_0',
            ),
            models.CheckConstraint(
                condition=models.Q(issue_qty_lac__gte=0),
                name='inv_cust_mth_issue_gte_0',
            ),
        ]

    def __str__(self):
        return f'{self.cust_product_id} {self.year}-{self.month:02d}'

    def clean(self):
        super().clean()
        if self.month is not None and (self.month < 1 or self.month > 12):
            raise ValidationError({'month': _('Month must be between 1 and 12.')})
        o = Decimal(str(self.opening_qty_lac or 0))
        r = Decimal(str(self.receipt_qty_lac or 0))
        i = Decimal(str(self.issue_qty_lac or 0))
        if o + r < i:
            raise ValidationError(
                _('Issued quantity cannot exceed opening plus received quantity.')
            )

    def closing_qty_lac(self) -> Decimal:
        o = Decimal(str(self.opening_qty_lac or 0))
        r = Decimal(str(self.receipt_qty_lac or 0))
        i = Decimal(str(self.issue_qty_lac or 0))
        q = Decimal('1').scaleb(-SO_QTY_DECIMAL_PLACES)
        return (o + r - i).quantize(q, rounding=ROUND_HALF_UP)


class InventoryStock(models.Model):
    """
    Centralized batch-level stock ledger (customer × product or item × batch).

    Multiple rows may share the same customer + SKU + batch number when older
    lines are **closed** (qty exhausted or year-end); at most one **open** row
    exists per that key. New inward/opening stock creates a new open row if
    only closed rows remain for the batch.

    **Closing:** batch lines with qty zero are marked closed for day-to-day
    uniqueness. When a **financial year** is closed in Utilities, any ledger
    rows still open that were **opened in that FY** are bulk-closed (year-end).
    """

    inv_id = models.AutoField(primary_key=True)

    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='inventory_stock_rows',
        verbose_name='Customer',
    )

    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        null=True,
        blank=True,
        related_name='inventory_stock_rows',
        verbose_name='Product',
    )

    item = models.ForeignKey(
        'masters.MstItem',
        on_delete=models.PROTECT,
        db_column='item_id',
        null=True,
        blank=True,
        related_name='inventory_stock_rows',
        verbose_name='Item',
    )

    # FG / RM / PM / … — mirrors masters.MstProdCat for the stocked SKU category.
    item_category = models.ForeignKey(
        'masters.MstProdCat',
        on_delete=models.PROTECT,
        db_column='item_type_id',
        related_name='inventory_stock_rows',
        verbose_name='Item category',
    )

    batch_no = models.CharField(max_length=100, default='', verbose_name='Batch no.')

    mfg_date = models.DateField(null=True, blank=True, verbose_name='Mfg date')
    exp_date = models.DateField(null=True, blank=True, verbose_name='Exp date')

    qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        verbose_name='Available qty',
    )

    reserved_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        verbose_name='Reserved qty',
        help_text='Reserved for future allocation (not decremented from available yet).',
    )

    last_trn_date = models.DateField(null=True, blank=True, verbose_name='Last transaction date')
    last_trn_type = models.CharField(max_length=30, blank=True, verbose_name='Last transaction type')
    ref_doc_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='Reference document id')
    ref_doc_type = models.CharField(max_length=30, blank=True, verbose_name='Reference document type')

    is_closed = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Closed',
        help_text='True when available qty is zero (operational batch close). Year-end FY close also finalises exhausted lines tied to that FY via Opened in FY.',
    )

    opened_in_fy = models.ForeignKey(
        'masters.FinancialYear',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_stock_opened_rows',
        verbose_name='Opened in FY',
        help_text='FY of first posting for this line (from transaction date). Used when closing a financial year.',
    )

    class Meta:
        db_table = 'InventoryStock'
        verbose_name = 'Inventory stock'
        verbose_name_plural = 'Inventory stock'
        ordering = ['customer', 'batch_no', 'product', 'item']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, item__isnull=True)
                    | models.Q(product__isnull=True, item__isnull=False)
                ),
                name='inv_stock_product_xor_item',
            ),
        ]

    def __str__(self):
        who = self.product_id or self.item_id
        return f'cust={self.customer_id} ref={who} batch={self.batch_no!r} qty={self.qty}'

    def clean(self):
        super().clean()
        flt = {
            'customer': self.customer,
            'batch_no': self.batch_no or '',
        }
        if self.product_id:
            flt['product_id'] = self.product_id
            flt['item__isnull'] = True
        elif self.item_id:
            flt['item_id'] = self.item_id
            flt['product__isnull'] = True
        else:
            raise ValidationError(_('Either product or item must be set.'))
        if self.is_closed:
            return
        qs = InventoryStock.objects.filter(**flt, is_closed=False)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                _('An open inventory row already exists for this customer, product or item, and batch number.')
            )


class TrnStkAdjHed(models.Model):
    """Stock adjustment / opening balance document header."""

    TYPE_OPENING = 'O'
    TYPE_ADJUST = 'A'
    TYPE_CHOICES = (
        (TYPE_OPENING, 'Opening balance'),
        (TYPE_ADJUST, 'Stock adjustment'),
    )

    stk_adj_id = models.AutoField(primary_key=True)
    stk_adj_dt = models.DateField(verbose_name='Document date')

    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='stock_adjustments',
        verbose_name='Customer',
    )

    stk_adj_type = models.CharField(
        max_length=1,
        choices=TYPE_CHOICES,
        verbose_name='Adjustment type',
    )

    item_type = models.ForeignKey(
        'masters.MstItemType',
        on_delete=models.PROTECT,
        db_column='item_type_id',
        related_name='stock_adjustments',
        verbose_name='Item type',
    )

    remarks = models.TextField(blank=True, null=True, verbose_name='Remarks')

    class Meta:
        db_table = 'TrnStkAdjHed'
        verbose_name = 'Stock adjustment (header)'
        verbose_name_plural = 'Stock adjustments (headers)'
        ordering = ['-stk_adj_dt', '-stk_adj_id']

    def __str__(self):
        return f'StkAdj {self.stk_adj_id} {self.stk_adj_dt}'


class TrnStkAdjDtl1(models.Model):
    """One product or item line per adjustment document."""

    dtl1_id = models.AutoField(primary_key=True)
    header = models.ForeignKey(
        TrnStkAdjHed,
        on_delete=models.CASCADE,
        db_column='stk_adj_id',
        related_name='lines',
        verbose_name='Adjustment',
    )

    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        null=True,
        blank=True,
        related_name='stock_adj_lines',
        verbose_name='Product',
    )

    item = models.ForeignKey(
        'masters.MstItem',
        on_delete=models.PROTECT,
        db_column='item_id',
        null=True,
        blank=True,
        related_name='stock_adj_lines',
        verbose_name='Item',
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        verbose_name='Quantity',
        help_text='Total of batch quantities (stored for reporting).',
    )

    line_remarks = models.CharField(max_length=20, blank=True, default='', verbose_name='Remarks')

    class Meta:
        db_table = 'TrnStkAdjDtl1'
        verbose_name = 'Stock adjustment line'
        verbose_name_plural = 'Stock adjustment lines'
        ordering = ['dtl1_id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, item__isnull=True)
                    | models.Q(product__isnull=True, item__isnull=False)
                ),
                name='stk_adj_dtl1_prod_xor_item',
            ),
            # Full (non-partial) uniques: MySQL allows multiple NULLs in a unique column, so
            # item-only rows still stack (header, NULL product); same for product lines and item.
            models.UniqueConstraint(
                fields=['header', 'product'],
                name='uniq_stk_adj_hed_product',
            ),
            models.UniqueConstraint(
                fields=['header', 'item'],
                name='uniq_stk_adj_hed_item',
            ),
        ]


class TrnStkAdjDtl2(models.Model):
    """Batch-level quantities for one adjustment line."""

    dtl2_id = models.AutoField(primary_key=True)
    line = models.ForeignKey(
        TrnStkAdjDtl1,
        on_delete=models.CASCADE,
        db_column='stk_adj_dtl1_id',
        related_name='batches',
        verbose_name='Line',
    )

    batch_no = models.CharField(max_length=100, verbose_name='Batch no.')
    mfg_date = models.DateField(null=True, blank=True, verbose_name='Mfg date')
    exp_date = models.DateField(null=True, blank=True, verbose_name='Exp date')

    batch_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        verbose_name='Batch qty',
    )

    class Meta:
        db_table = 'TrnStkAdjDtl2'
        verbose_name = 'Stock adjustment batch'
        verbose_name_plural = 'Stock adjustment batches'
        ordering = ['dtl2_id']
