from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0022_sales_invoice_ref_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='trnslsorddtl1',
            name='is_sale_completed',
            field=models.BooleanField(
                default=False,
                help_text='True when all log-sheet batches for this line have been fully invoiced.',
                verbose_name='Sale completed',
            ),
        ),
    ]
