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


class StockHed(models.Model):
    """
    Central current stock balance table.

    RM/PM key: financial_year + customer + item (unbatched, item-wise).
    FG key: financial_year + customer + product + batch_no (batch-wise).

    Business rule: closing_qty = opn_qty + rcpt_qty - issue_qty.
    """

    stock_lnkno = models.AutoField(
        primary_key=True,
        db_column='stock_lnkno',
        verbose_name=_('Stock link no.'),
    )

    op_date = models.DateField(
        db_column='op_date',
        verbose_name=_('Opening/cutover date'),
        help_text=_('Date when this stock row was opened or cut over.'),
    )

    financial_year = models.ForeignKey(
        'masters.FinancialYear',
        on_delete=models.PROTECT,
        db_column='financial_year_id',
        related_name='stock_hed_rows',
        verbose_name=_('Financial year'),
    )

    customer = models.ForeignKey(
        'masters.MstCust',
        on_delete=models.PROTECT,
        db_column='cust_id',
        related_name='stock_hed_rows',
        verbose_name=_('Customer'),
    )

    item = models.ForeignKey(
        'masters.MstItem',
        on_delete=models.PROTECT,
        db_column='item_id',
        null=True,
        blank=True,
        related_name='stock_hed_rows',
        verbose_name=_('Item (RM/PM)'),
    )

    product = models.ForeignKey(
        'masters.MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        null=True,
        blank=True,
        related_name='stock_hed_rows',
        verbose_name=_('Product (FG)'),
    )

    item_category = models.ForeignKey(
        'masters.MstProdCat',
        on_delete=models.PROTECT,
        db_column='item_type_id',
        null=True,
        blank=True,
        related_name='stock_hed_rows',
        verbose_name=_('Item category'),
    )

    batch_no = models.CharField(
        max_length=100,
        default='',
        blank=True,
        db_column='batch_no',
        verbose_name=_('Batch no.'),
        help_text=_('Blank for RM/PM; required for FG.'),
    )

    mfg_date = models.DateField(
        null=True,
        blank=True,
        db_column='mfg_date',
        verbose_name=_('Mfg date'),
        help_text=_('FG only.'),
    )

    exp_date = models.DateField(
        null=True,
        blank=True,
        db_column='exp_date',
        verbose_name=_('Exp date'),
        help_text=_('FG only.'),
    )

    opn_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        db_column='opn_qty',
        verbose_name=_('Opening quantity'),
    )

    rcpt_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        db_column='rcpt_qty',
        verbose_name=_('Total receipts'),
    )

    issue_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        db_column='issue_qty',
        verbose_name=_('Total issues'),
    )

    closing_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        db_column='closing_qty',
        verbose_name=_('Closing balance'),
        help_text=_('Stored running balance = opn_qty + rcpt_qty - issue_qty.'),
    )

    reserved_qty = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        default=Decimal('0'),
        db_column='reserved_qty',
        verbose_name=_('Reserved quantity'),
    )

    is_closed = models.BooleanField(
        default=False,
        db_index=True,
        db_column='is_closed',
        verbose_name=_('Is closed'),
        help_text=_('True when closing balance is zero and no reserved quantity exists.'),
    )

    last_trn_date = models.DateField(
        null=True,
        blank=True,
        db_column='last_trn_date',
        verbose_name=_('Last transaction date'),
    )

    last_trn_type = models.CharField(
        max_length=30,
        blank=True,
        default='',
        db_column='last_trn_type',
        verbose_name=_('Last transaction type'),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column='created_at',
        verbose_name=_('Created at'),
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_column='updated_at',
        verbose_name=_('Updated at'),
    )

    class Meta:
        db_table = 'StockHed'
        verbose_name = _('Stock balance header')
        verbose_name_plural = _('Stock balance headers')
        ordering = ['customer', 'product', 'item', 'batch_no']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, item__isnull=True)
                    | models.Q(product__isnull=True, item__isnull=False)
                ),
                name='stock_hed_product_xor_item',
            ),
            models.CheckConstraint(
                condition=models.Q(closing_qty__gte=0),
                name='stock_hed_closing_gte_0',
            ),
            # MySQL-compatible unique constraints (full columns, no conditional WHERE clause):
            # For RM/PM: item is filled, product is NULL. Multiple NULLs in product do not conflict in MySQL.
            models.UniqueConstraint(
                fields=['financial_year', 'customer', 'item'],
                name='unique_stock_hed_fy_cust_item',
            ),
            # For FG: product is filled, item is NULL. Multiple NULLs in item do not conflict in MySQL.
            models.UniqueConstraint(
                fields=['financial_year', 'customer', 'product', 'batch_no'],
                name='unique_stock_hed_fy_cust_prod_batch',
            ),
        ]

    def __str__(self):
        sku = f'prod={self.product_id}' if self.product_id else f'item={self.item_id}'
        return f'StockHed#{self.stock_lnkno} {sku} batch={self.batch_no!r} closing={self.closing_qty}'

    def calculate_closing_qty(self) -> Decimal:
        step = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)
        o = Decimal(str(self.opn_qty or 0))
        r = Decimal(str(self.rcpt_qty or 0))
        i = Decimal(str(self.issue_qty or 0))
        return (o + r - i).quantize(step, rounding=ROUND_HALF_UP)

    def clean(self):
        super().clean()
        if bool(self.product_id) == bool(self.item_id):
            raise ValidationError(_('Exactly one of item or product must be set.'))

        if self.item_id:
            if (self.batch_no or '').strip():
                raise ValidationError({'batch_no': _('RM/PM inventory is item-wise only; batch number must be blank.')})
            if self.mfg_date or self.exp_date:
                raise ValidationError(_('RM/PM inventory cannot have manufacturing or expiry dates.'))
            self.batch_no = ''
            self.mfg_date = None
            self.exp_date = None
        else:
            if not (self.batch_no or '').strip():
                raise ValidationError({'batch_no': _('Finished goods inventory is batch-wise; batch number is required.')})
            if self.mfg_date and self.exp_date and self.exp_date < self.mfg_date:
                raise ValidationError(_('Expiry date cannot be before manufacturing date.'))

        expected = self.calculate_closing_qty()
        if self.closing_qty != expected:
            raise ValidationError(
                _('Closing quantity ({actual}) must equal opening ({op}) + receipt ({rc}) - issue ({iss}) = {exp}.').format(
                    actual=self.closing_qty,
                    op=self.opn_qty,
                    rc=self.rcpt_qty,
                    iss=self.issue_qty,
                    exp=expected,
                )
            )
        if self.closing_qty < 0:
            raise ValidationError(_('Closing quantity cannot be negative.'))

    def save(self, *args, **kwargs):
        if self.item_id:
            self.batch_no = ''
            self.mfg_date = None
            self.exp_date = None
            if not self.item_category_id and self.item_id:
                self.item_category_id = self.item.item_category_id
        elif self.product_id:
            self.batch_no = (self.batch_no or '').strip()
            if not self.item_category_id and self.product_id:
                self.item_category_id = self.product.prod_category_id

        self.closing_qty = self.calculate_closing_qty()
        if self.closing_qty < 0:
            raise ValidationError(_('Closing quantity cannot be negative.'))
        self.is_closed = (self.closing_qty == 0 and Decimal(str(self.reserved_qty or 0)) == 0)
        super().save(*args, **kwargs)


class StockDtl(models.Model):
    """
    Immutable stock movement-history table.

    Records every individual stock movement (Opening, Inward, Dispensing, DPR, Sales, Stock Adj).
    Reversals are recorded as compensating movement rows with is_reversal=True and reversal_of link.
    """

    TRAN_OPN = 'OPN'
    TRAN_INW = 'INW'
    TRAN_DIS = 'DIS'
    TRAN_DPR = 'DPR'
    TRAN_SLS = 'SLS'
    TRAN_STK = 'STK'

    TRAN_ID_CHOICES = (
        (TRAN_OPN, _('Opening balance')),
        (TRAN_INW, _('Inward RM/PM')),
        (TRAN_DIS, _('RM Dispensing')),
        (TRAN_DPR, _('DPR Finished Goods')),
        (TRAN_SLS, _('Sales Invoice Dispatch')),
        (TRAN_STK, _('Stock Adjustment')),
    )

    TYPE_OPENING = 'O'
    TYPE_RECEIPT = 'R'
    TYPE_ISSUE = 'I'

    TRN_TYPE_CHOICES = (
        (TYPE_OPENING, _('Opening')),
        (TYPE_RECEIPT, _('Receipt')),
        (TYPE_ISSUE, _('Issue')),
    )

    stock_dtl_id = models.AutoField(
        primary_key=True,
        db_column='stock_dtl_id',
        verbose_name=_('Stock detail ID'),
    )

    stock = models.ForeignKey(
        StockHed,
        on_delete=models.PROTECT,
        db_column='stock_lnkno',
        related_name='movements',
        verbose_name=_('Stock header'),
    )

    tran_id = models.CharField(
        max_length=10,
        choices=TRAN_ID_CHOICES,
        db_column='tran_id',
        verbose_name=_('Source module code'),
    )

    trn_type = models.CharField(
        max_length=1,
        choices=TRN_TYPE_CHOICES,
        db_column='trn_type',
        verbose_name=_('Movement type'),
        help_text=_('O = Opening, R = Receipt, I = Issue.'),
    )

    trn_no = models.CharField(
        max_length=50,
        db_column='trn_no',
        verbose_name=_('Originating document number/id'),
    )

    trn_date = models.DateField(
        db_column='trn_date',
        verbose_name=_('Transaction date'),
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=QTY_DECIMAL_PLACES,
        db_column='quantity',
        verbose_name=_('Movement quantity'),
    )

    source_line_id = models.CharField(
        max_length=100,
        db_column='source_line_id',
        db_index=True,
        verbose_name=_('Source line / idempotency key'),
        help_text=_('Idempotency key ensuring a document line cannot post twice.'),
    )

    is_reversal = models.BooleanField(
        default=False,
        db_column='is_reversal',
        verbose_name=_('Is reversal'),
        help_text=_('True if this movement reverses a previous movement.'),
    )

    reversal_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='reversal_of_id',
        related_name='reversals',
        verbose_name=_('Reversal of movement'),
    )

    remarks = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_column='remarks',
        verbose_name=_('Remarks'),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column='created_at',
        verbose_name=_('Created at'),
    )

    class Meta:
        db_table = 'StockDtl'
        verbose_name = _('Stock movement detail')
        verbose_name_plural = _('Stock movement details')
        ordering = ['trn_date', 'stock_dtl_id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='stock_dtl_quantity_gt_0',
            ),
            models.UniqueConstraint(
                fields=['source_line_id'],
                name='unique_stock_dtl_source_line_id',
            ),
        ]

    def __str__(self):
        rev = ' [REV]' if self.is_reversal else ''
        return f'StockDtl#{self.stock_dtl_id} {self.tran_id}/{self.trn_type} qty={self.quantity}{rev} ({self.source_line_id})'


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
