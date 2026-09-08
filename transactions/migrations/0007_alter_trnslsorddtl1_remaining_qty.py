# Align sales order line remaining_qty with SO_QTY_DECIMAL_PLACES (not log sheet).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0006_trn_logsheet'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trnslsorddtl1',
            name='remaining_qty',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Remaining quantity to allocate (in Lakhs).',
                max_digits=10,
                verbose_name='Remaining qty',
            ),
        ),
    ]
