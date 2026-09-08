from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('masters', '0006_mstitem_sample_qty'),
    ]

    operations = [
        migrations.AddField(
            model_name='mstbomrmdtl',
            name='machine',
            field=models.ForeignKey(
                blank=True,
                db_column='machine_id',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='bom_rm_items',
                to='masters.mstmachine',
                verbose_name='Machine',
            ),
        ),
        migrations.AddField(
            model_name='mstbomrmdtl',
            name='no_of_lots',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='No. of lots'),
        ),
        migrations.AddField(
            model_name='mstbomrmdtl',
            name='section',
            field=models.ForeignKey(
                blank=True,
                db_column='section_id',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='bom_rm_items',
                to='masters.mstsection',
                verbose_name='Section',
            ),
        ),
    ]
