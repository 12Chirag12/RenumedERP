from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0003_sales_order_remaining_qty'),
    ]

    operations = [
        migrations.AddField(
            model_name='trnbatchhed',
            name='order_line',
            field=models.ForeignKey(
                db_column='order_dtl1_id',
                help_text='Specific sales order detail line this batch allocation belongs to.',
                on_delete=models.deletion.CASCADE,
                related_name='batch_headers',
                to='transactions.trnslsorddtl1',
                verbose_name='Sales order line',
            ),
        ),
    ]

