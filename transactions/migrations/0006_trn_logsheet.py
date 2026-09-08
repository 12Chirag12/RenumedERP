# Single migration for Trn_LogSheet (granulation log sheet), including layer_slot / double-layer support.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('masters', '0002_alter_mstsupplier_short_name_nullable'),
        ('transactions', '0005_nos_integer_and_qty_2dp'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrnLogSheet',
            fields=[
                ('logsheet_id', models.AutoField(primary_key=True, serialize=False)),
                ('gran_dt', models.DateField(verbose_name='Granulation date')),
                (
                    'shift_id',
                    models.CharField(
                        choices=[('Day', 'Day'), ('Night', 'Night')],
                        db_column='shift_id',
                        max_length=5,
                        verbose_name='Shift',
                    ),
                ),
                ('blend_dt', models.DateField(blank=True, null=True, verbose_name='Blending date')),
                (
                    'dpr_flg',
                    models.CharField(
                        choices=[('Y', 'Yes'), ('N', 'No')],
                        default='N',
                        max_length=1,
                        verbose_name='DPR flag',
                    ),
                ),
                (
                    'layer_slot',
                    models.CharField(
                        choices=[
                            ('S', 'Single layer'),
                            ('1', 'First colour'),
                            ('2', 'Second colour'),
                        ],
                        default='S',
                        help_text='S = single-layer batch; 1 / 2 = first or second colour for double-layer.',
                        max_length=1,
                        verbose_name='Layer / colour slot',
                    ),
                ),
                (
                    'batch_line',
                    models.ForeignKey(
                        db_column='batch_id',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='log_sheets',
                        to='transactions.trnbatchdtl',
                        verbose_name='Batch allocation line',
                    ),
                ),
                (
                    'customer',
                    models.ForeignKey(
                        db_column='cust_id',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='log_sheets',
                        to='masters.mstcust',
                        verbose_name='Customer',
                    ),
                ),
                (
                    'product',
                    models.ForeignKey(
                        db_column='prod_id',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='log_sheets',
                        to='masters.mstprod',
                        verbose_name='Product',
                    ),
                ),
                (
                    'section',
                    models.ForeignKey(
                        db_column='section_id',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='log_sheets',
                        to='masters.mstsection',
                        verbose_name='Section',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Log sheet',
                'verbose_name_plural': 'Log sheets',
                'db_table': 'Trn_LogSheet',
                'ordering': ['-gran_dt', '-logsheet_id'],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('batch_line', 'layer_slot'),
                        name='unique_trn_logsheet_batch_layer_slot',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(shift_id__in=['Day', 'Night']),
                        name='trn_logsheet_shift_enum',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(dpr_flg__in=['Y', 'N']),
                        name='trn_logsheet_dpr_enum',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(layer_slot__in=['S', '1', '2']),
                        name='trn_logsheet_layer_slot_enum',
                    ),
                ],
            },
        ),
    ]
