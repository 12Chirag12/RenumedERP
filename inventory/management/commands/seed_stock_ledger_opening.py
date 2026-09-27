"""
Management command to seed initial StockHed and StockDtl ledger balances
from existing InventoryStock balances.

Usage:
  python manage.py seed_stock_ledger_opening --opening-date 2026-04-01 --financial-year 2026-27 --dry-run
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date

from masters.models import FinancialYear
from transactions.constants import QTY_DECIMAL_PLACES
from transactions.utils import get_or_create_financial_year_for_date

from inventory.models import InventoryStock, StockDtl, StockHed

_QUANT = Decimal('1').scaleb(-QTY_DECIMAL_PLACES)


def _q(d) -> Decimal:
    return Decimal(str(d or 0)).quantize(_QUANT, rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = (
        'Idempotently seed StockHed and StockDtl opening records from existing '
        'InventoryStock rows with dry-run support and reconciliation reporting.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--opening-date',
            type=str,
            required=True,
            help='Opening/cutover date in YYYY-MM-DD format (e.g. 2026-04-01).',
        )
        parser.add_argument(
            '--financial-year',
            type=str,
            required=False,
            help='Financial year display or code (e.g. 2026-27). Defaults to FY of opening-date.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate cutover and produce reconciliation report without committing changes.',
        )

    def handle(self, *args, **options):
        raw_date = options['opening_date']
        op_date = parse_date(raw_date.strip())
        if not op_date:
            raise CommandError(f'Invalid date format: {raw_date!r}. Expected YYYY-MM-DD.')

        fy_raw = (options.get('financial_year') or '').strip()
        if fy_raw:
            fy = (
                FinancialYear.objects.filter(
                    Q(fy_code__iexact=fy_raw) | Q(fy_display__iexact=fy_raw)
                )
                .order_by('pk')
                .first()
            )
            if not fy:
                raise CommandError(f'FinancialYear matching {fy_raw!r} not found.')
        else:
            fy = get_or_create_financial_year_for_date(op_date)

        dry_run = options['dry_run']

        self.stdout.write(self.style.MIGRATE_HEADING('=== Stock Ledger Opening Cutover ==='))
        self.stdout.write(f'Opening / Cutover Date: {op_date}')
        self.stdout.write(f'Financial Year:        {fy.fy_display} (ID: {fy.pk})')
        self.stdout.write(f'Mode:                  {"DRY RUN (no DB changes)" if dry_run else "LIVE COMMIT"}')
        self.stdout.write('')

        # Scan active InventoryStock rows
        inv_qs = (
            InventoryStock.objects.filter(is_closed=False, qty__gt=0)
            .select_related('customer', 'product', 'product__uom', 'item', 'item__uom', 'item_category')
            .order_by('customer_id', 'product_id', 'item_id', 'batch_no')
        )

        total_scanned = inv_qs.count()
        if total_scanned == 0:
            self.stdout.write(self.style.WARNING('No open InventoryStock rows with qty > 0 found.'))
            return

        reconciliation_records = []
        rm_pm_groups: dict[tuple[int, int], list[InventoryStock]] = defaultdict(list)
        fg_rows: list[InventoryStock] = []

        for row in inv_qs:
            if row.item_id:
                rm_pm_groups[(row.customer_id, row.item_id)].append(row)
            else:
                fg_rows.append(row)

        created_hed_count = 0
        created_dtl_count = 0
        skipped_dtl_count = 0
        total_qty_converted = Decimal('0')

        with transaction.atomic():
            # Process RM/PM item-wise groups
            for (cust_id, itm_id), rows in rm_pm_groups.items():
                first_row = rows[0]
                cust = first_row.customer
                item = first_row.item
                total_grp_qty = _q(sum(r.qty for r in rows))
                total_grp_rsv = _q(sum(r.reserved_qty for r in rows))

                stock_hed = StockHed.objects.filter(
                    financial_year=fy,
                    customer_id=cust_id,
                    item_id=itm_id,
                    product_id__isnull=True,
                ).first()

                hed_is_new = False
                if stock_hed is None:
                    hed_is_new = True
                    stock_hed = StockHed.objects.create(
                        op_date=op_date,
                        financial_year=fy,
                        customer_id=cust_id,
                        item_id=itm_id,
                        product_id=None,
                        item_category_id=item.item_category_id,
                        batch_no='',
                        mfg_date=None,
                        exp_date=None,
                        opn_qty=Decimal('0'),
                        rcpt_qty=Decimal('0'),
                        issue_qty=Decimal('0'),
                        closing_qty=Decimal('0'),
                        reserved_qty=total_grp_rsv,
                        is_closed=False,
                        last_trn_date=op_date,
                        last_trn_type='OPN/O',
                    )
                    created_hed_count += 1

                for inv_row in rows:
                    source_id = f'OPN:inv:{inv_row.pk}'
                    if StockDtl.objects.filter(source_line_id=source_id).exists():
                        skipped_dtl_count += 1
                        reconciliation_records.append({
                            'type': 'RM/PM',
                            'customer': cust.cust_name,
                            'sku': item.item_name,
                            'batch': '- (unbatched)',
                            'inv_qty': _q(inv_row.qty),
                            'hed_qty': stock_hed.closing_qty,
                            'status': 'ALREADY_SEEDED',
                        })
                        continue

                    # Atomically update StockHed opening & closing
                    stock_hed.opn_qty = _q(stock_hed.opn_qty + inv_row.qty)
                    stock_hed.closing_qty = stock_hed.calculate_closing_qty()
                    stock_hed.is_closed = (stock_hed.closing_qty == 0 and stock_hed.reserved_qty == 0)
                    stock_hed.save(update_fields=['opn_qty', 'closing_qty', 'is_closed', 'updated_at'])

                    StockDtl.objects.create(
                        stock=stock_hed,
                        tran_id=StockDtl.TRAN_OPN,
                        trn_type=StockDtl.TYPE_OPENING,
                        trn_no=f'INV-{inv_row.pk}',
                        trn_date=op_date,
                        quantity=_q(inv_row.qty),
                        source_line_id=source_id,
                        is_reversal=False,
                        remarks=f'Cutover opening balance from InventoryStock #{inv_row.pk}',
                    )
                    created_dtl_count += 1
                    total_qty_converted += _q(inv_row.qty)

                    reconciliation_records.append({
                        'type': 'RM/PM',
                        'customer': cust.cust_name,
                        'sku': item.item_name,
                        'batch': '- (unbatched)',
                        'inv_qty': _q(inv_row.qty),
                        'hed_qty': stock_hed.closing_qty,
                        'status': 'SEEDED' if not dry_run else 'WOULD_SEED',
                    })

            # Process FG rows (batch-wise)
            for inv_row in fg_rows:
                cust = inv_row.customer
                prod = inv_row.product
                bn = (inv_row.batch_no or '').strip()
                if not bn:
                    bn = f'BATCH-{inv_row.pk}'

                source_id = f'OPN:inv:{inv_row.pk}'
                if StockDtl.objects.filter(source_line_id=source_id).exists():
                    skipped_dtl_count += 1
                    reconciliation_records.append({
                        'type': 'FG',
                        'customer': cust.cust_name,
                        'sku': prod.prod_name,
                        'batch': bn,
                        'inv_qty': _q(inv_row.qty),
                        'hed_qty': _q(inv_row.qty),
                        'status': 'ALREADY_SEEDED',
                    })
                    continue

                stock_hed = StockHed.objects.filter(
                    financial_year=fy,
                    customer_id=cust.pk,
                    product_id=prod.pk,
                    batch_no=bn,
                    item_id__isnull=True,
                ).first()

                if stock_hed is None:
                    stock_hed = StockHed.objects.create(
                        op_date=op_date,
                        financial_year=fy,
                        customer_id=cust.pk,
                        product_id=prod.pk,
                        item_id=None,
                        item_category_id=prod.prod_category_id,
                        batch_no=bn,
                        mfg_date=inv_row.mfg_date,
                        exp_date=inv_row.exp_date,
                        opn_qty=_q(inv_row.qty),
                        rcpt_qty=Decimal('0'),
                        issue_qty=Decimal('0'),
                        closing_qty=_q(inv_row.qty),
                        reserved_qty=_q(inv_row.reserved_qty),
                        is_closed=False,
                        last_trn_date=op_date,
                        last_trn_type='OPN/O',
                    )
                    created_hed_count += 1
                else:
                    stock_hed.opn_qty = _q(stock_hed.opn_qty + inv_row.qty)
                    stock_hed.closing_qty = stock_hed.calculate_closing_qty()
                    stock_hed.is_closed = (stock_hed.closing_qty == 0 and stock_hed.reserved_qty == 0)
                    stock_hed.save(update_fields=['opn_qty', 'closing_qty', 'is_closed', 'updated_at'])

                StockDtl.objects.create(
                    stock=stock_hed,
                    tran_id=StockDtl.TRAN_OPN,
                    trn_type=StockDtl.TYPE_OPENING,
                    trn_no=f'INV-{inv_row.pk}',
                    trn_date=op_date,
                    quantity=_q(inv_row.qty),
                    source_line_id=source_id,
                    is_reversal=False,
                    remarks=f'Cutover opening balance from InventoryStock #{inv_row.pk}',
                )
                created_dtl_count += 1
                total_qty_converted += _q(inv_row.qty)

                reconciliation_records.append({
                    'type': 'FG',
                    'customer': cust.cust_name,
                    'sku': prod.prod_name,
                    'batch': bn,
                    'inv_qty': _q(inv_row.qty),
                    'hed_qty': stock_hed.closing_qty,
                    'status': 'SEEDED' if not dry_run else 'WOULD_SEED',
                })

            if dry_run:
                transaction.set_rollback(True)

        # Print reconciliation summary
        self.stdout.write(self.style.MIGRATE_HEADING('--- Reconciliation Report ---'))
        self.stdout.write(f'InventoryStock Rows Scanned:   {total_scanned}')
        self.stdout.write(f'RM/PM Unique Items:            {len(rm_pm_groups)}')
        self.stdout.write(f'FG Batches:                    {len(fg_rows)}')
        self.stdout.write(f'StockHed Rows {"Would Create" if dry_run else "Created"}:       {created_hed_count}')
        self.stdout.write(f'StockDtl Movements {"Would Create" if dry_run else "Created"}:  {created_dtl_count}')
        self.stdout.write(f'StockDtl Movements Skipped:    {skipped_dtl_count}')
        self.stdout.write(f'Total Quantity Converted:      {total_qty_converted}')
        self.stdout.write('')

        # Table report
        col_fmt = '{:<6} | {:<20} | {:<30} | {:<16} | {:>10} | {:>10} | {:<15}'
        self.stdout.write(col_fmt.format('TYPE', 'CUSTOMER', 'SKU', 'BATCH', 'INV_QTY', 'HED_QTY', 'STATUS'))
        self.stdout.write('-' * 115)
        for r in reconciliation_records[:50]:
            self.stdout.write(
                col_fmt.format(
                    r['type'],
                    r['customer'][:20],
                    r['sku'][:30],
                    r['batch'][:16],
                    str(r['inv_qty']),
                    str(r['hed_qty']),
                    r['status'],
                )
            )
        if len(reconciliation_records) > 50:
            self.stdout.write(f'... and {len(reconciliation_records) - 50} more row(s) reconciled.')

        self.stdout.write('-' * 115)
        if dry_run:
            self.stdout.write(self.style.SUCCESS('[DRY RUN COMPLETE] No database records were created or modified.'))
        else:
            self.stdout.write(self.style.SUCCESS('[CUTOVER COMPLETE] Opening balances successfully seeded into StockHed and StockDtl.'))
