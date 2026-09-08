# Generated manually for FY-linked inventory closing.

from django.db import migrations, models


def _fy_start_year_for_date(d):
    if d.month >= 4:
        return d.year
    return d.year - 1


def backfill_opened_in_fy(apps, schema_editor):
    InventoryStock = apps.get_model('inventory', 'InventoryStock')
    FinancialYear = apps.get_model('masters', 'FinancialYear')

    for row in InventoryStock.objects.filter(opened_in_fy__isnull=True).iterator(chunk_size=500):
        d = row.last_trn_date
        if not d:
            continue
        fy_start = _fy_start_year_for_date(d)
        fy = FinancialYear.objects.filter(fy_start_year=fy_start).first()
        if fy:
            InventoryStock.objects.filter(pk=row.pk).update(opened_in_fy_id=fy.fy_id)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_inventory_stock_is_closed'),
        ('masters', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventorystock',
            name='opened_in_fy',
            field=models.ForeignKey(
                blank=True,
                help_text='FY of first posting for this line (from transaction date). Used when closing a financial year.',
                null=True,
                on_delete=models.PROTECT,
                related_name='inventory_stock_opened_rows',
                to='masters.financialyear',
                verbose_name='Opened in FY',
            ),
        ),
        migrations.RunPython(backfill_opened_in_fy, noop),
    ]
