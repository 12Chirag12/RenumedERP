from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0002_trn_batch_hed_dtl'),
    ]

    operations = [
        migrations.AddField(
            model_name='trnslsorddtl1',
            name='remaining_qty',
            field=models.DecimalField(
                decimal_places=5,
                default=0,
                help_text='Remaining quantity to allocate (in Lakhs).',
                max_digits=10,
                verbose_name='Remaining qty',
            ),
        ),
        migrations.AddField(
            model_name='trnslsorddtl1',
            name='is_completed',
            field=models.BooleanField(
                default=False,
                help_text='True when remaining qty reaches 0.',
                verbose_name='Completed',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='trnslsorddtl1',
            name='unique_trn_sls_ord_line_prod',
        ),
        migrations.AddConstraint(
            model_name='trnslsorddtl1',
            constraint=models.UniqueConstraint(
                fields=('order', 'product', 'packing_style', 'rate'),
                name='unique_trn_sls_ord_line_triplet',
            ),
        ),
        migrations.AddConstraint(
            model_name='trnslsorddtl1',
            constraint=models.CheckConstraint(
                condition=Q(remaining_qty__gte=0),
                name='trn_sls_dtl1_remaining_gte_0',
            ),
        ),
    ]

