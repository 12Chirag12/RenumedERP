# Merge duplicate InventoryStock rows (same customer + product/item + batch_no),
# then replace unique constraints so the ledger key is customer × SKU × batch no. only.

from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


def _q(d, places=3):
    step = Decimal('1').scaleb(-places)
    return Decimal(str(d or 0)).quantize(step, rounding=ROUND_HALF_UP)


def merge_duplicate_inventory_rows(apps, schema_editor):
    InventoryStock = apps.get_model('inventory', 'InventoryStock')
    from collections import defaultdict

    groups = defaultdict(list)
    for row in InventoryStock.objects.all().iterator():
        bn = (row.batch_no or '').strip()
        if row.product_id:
            key = ('P', row.customer_id, row.product_id, bn)
        elif row.item_id:
            key = ('I', row.customer_id, row.item_id, bn)
        else:
            continue
        groups[key].append(row.pk)

    for _key, pks in groups.items():
        if len(pks) <= 1:
            continue
        rows = list(InventoryStock.objects.filter(pk__in=pks).order_by('inv_id'))
        keep = rows[0]
        total_qty = _q(sum(Decimal(str(r.qty or 0)) for r in rows))
        total_rsv = _q(sum(Decimal(str(r.reserved_qty or 0)) for r in rows))
        last = rows[-1]
        for r in rows[1:]:
            r.delete()
        keep.qty = total_qty
        keep.reserved_qty = total_rsv
        keep.mfg_date = last.mfg_date
        keep.exp_date = last.exp_date
        keep.last_trn_date = last.last_trn_date
        keep.last_trn_type = last.last_trn_type or ''
        keep.ref_doc_id = last.ref_doc_id
        keep.ref_doc_type = last.ref_doc_type or ''
        keep.save(
            update_fields=[
                'qty',
                'reserved_qty',
                'mfg_date',
                'exp_date',
                'last_trn_date',
                'last_trn_type',
                'ref_doc_id',
                'ref_doc_type',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_inventory_stock_and_adjustment'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_inventory_rows, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='inventorystock',
            name='inv_stock_uniq_cust_prod_batch',
        ),
        migrations.RemoveConstraint(
            model_name='inventorystock',
            name='inv_stock_uniq_cust_item_batch',
        ),
        migrations.AddConstraint(
            model_name='inventorystock',
            constraint=models.UniqueConstraint(
                condition=models.Q(('product__isnull', False)),
                fields=('customer', 'product', 'batch_no'),
                name='inv_stock_uniq_cust_prod_batch_no',
            ),
        ),
        migrations.AddConstraint(
            model_name='inventorystock',
            constraint=models.UniqueConstraint(
                condition=models.Q(('item__isnull', False)),
                fields=('customer', 'item', 'batch_no'),
                name='inv_stock_uniq_cust_item_batch_no',
            ),
        ),
    ]
