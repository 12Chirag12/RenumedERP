from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0004_batch_hed_order_line'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trnslsorddtl1',
            name='ord_qty_nos',
            field=models.DecimalField(decimal_places=0, default=0, max_digits=12, verbose_name='Order qty (nos.)'),
        ),
        migrations.AlterField(
            model_name='trnbatchhed',
            name='batch_size_n',
            field=models.DecimalField(decimal_places=0, max_digits=12, verbose_name='Batch size (Nos.)'),
        ),
        migrations.AlterField(
            model_name='trnbatchhed',
            name='partial_qty_n',
            field=models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True, verbose_name='Partial qty (Nos.)'),
        ),
        migrations.AlterField(
            model_name='trnbatchdtl',
            name='batch_qty_n',
            field=models.DecimalField(decimal_places=0, max_digits=12, verbose_name='Batch qty (Nos.)'),
        ),
    ]

