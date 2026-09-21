"""Consolidate live RM/PM inventory into item-level, unbatched buckets."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


def _q(value, places=3):
    step = Decimal('1').scaleb(-places)
    return Decimal(str(value or 0)).quantize(step, rounding=ROUND_HALF_UP)


def consolidate_rm_pm_item_stock(apps, schema_editor):
    InventoryStock = apps.get_model('inventory', 'InventoryStock')

    groups = defaultdict(list)
    rows = (
        InventoryStock.objects.filter(
            product_id__isnull=True,
            item_id__isnull=False,
            item_category_id__in=('RM', 'PM'),
            is_closed=False,
        )
        .order_by('customer_id', 'item_id', 'inv_id')
    )
    for row in rows.iterator():
        groups[(row.customer_id, row.item_id, row.item_category_id)].append(row)

    for group_rows in groups.values():
        # Prefer an existing unbatched row so its opening-FY identity survives.
        keep = next((row for row in group_rows if not (row.batch_no or '').strip()), group_rows[0])
        latest = max(
            group_rows,
            key=lambda row: (row.last_trn_date is not None, row.last_trn_date, row.inv_id),
        )
        total_qty = _q(sum(Decimal(str(row.qty or 0)) for row in group_rows))
        total_reserved = _q(sum(Decimal(str(row.reserved_qty or 0)) for row in group_rows))
        opened_in_fy_id = keep.opened_in_fy_id or next(
            (row.opened_in_fy_id for row in group_rows if row.opened_in_fy_id),
            None,
        )

        InventoryStock.objects.filter(
            pk__in=[row.pk for row in group_rows if row.pk != keep.pk]
        ).delete()

        keep.batch_no = ''
        keep.mfg_date = None
        keep.exp_date = None
        keep.qty = total_qty
        keep.reserved_qty = total_reserved if total_qty > 0 else _q(0)
        keep.is_closed = total_qty <= 0
        keep.opened_in_fy_id = opened_in_fy_id
        keep.last_trn_date = latest.last_trn_date
        keep.last_trn_type = latest.last_trn_type or ''
        keep.ref_doc_id = latest.ref_doc_id
        keep.ref_doc_type = latest.ref_doc_type or ''
        keep.save(
            update_fields=[
                'batch_no',
                'mfg_date',
                'exp_date',
                'qty',
                'reserved_qty',
                'is_closed',
                'opened_in_fy',
                'last_trn_date',
                'last_trn_type',
                'ref_doc_id',
                'ref_doc_type',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_mysql_compatible_uniques'),
    ]

    operations = [
        migrations.RunPython(consolidate_rm_pm_item_stock, migrations.RunPython.noop),
    ]
