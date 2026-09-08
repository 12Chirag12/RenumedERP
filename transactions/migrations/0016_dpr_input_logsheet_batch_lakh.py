# DPR: log sheet links on TrnDprInputBatch + batch_size_lakh on TrnDpr

import django.db.models.deletion
from django.db import migrations, models


def forwards_input_link_logsheet(apps, schema_editor):
    TrnDprInputBatch = apps.get_model('transactions', 'TrnDprInputBatch')
    TrnLogSheet = apps.get_model('transactions', 'TrnLogSheet')
    for ib in TrnDprInputBatch.objects.all():
        bid = getattr(ib, 'batch_line_id', None)
        if not bid:
            ib.delete()
            continue
        ls = TrnLogSheet.objects.filter(batch_line_id=bid).order_by('logsheet_id').first()
        if ls:
            ib.log_sheet_id = ls.pk
            ib.save(update_fields=['log_sheet_id'])
        else:
            ib.delete()


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0015_trn_dpr_input_batch'),
    ]

    operations = [
        migrations.AddField(
            model_name='trndpr',
            name='batch_size_lakh',
            field=models.DecimalField(
                blank=True,
                db_column='Batch_size_lakh',
                decimal_places=5,
                help_text='Granulation / lubrication multi-batch DPR: manual batch size in lac.',
                max_digits=12,
                null=True,
                verbose_name='Batch size (Lakh)',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='trndprinputbatch',
            name='unique_dpr_input_batch_line',
        ),
        migrations.AddField(
            model_name='trndprinputbatch',
            name='log_sheet',
            field=models.ForeignKey(
                blank=True,
                db_column='LogSheet_id',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='dpr_input_links',
                to='transactions.trnlogsheet',
                verbose_name='Log sheet',
            ),
        ),
        migrations.RunPython(forwards_input_link_logsheet, backwards_noop),
        migrations.RemoveField(
            model_name='trndprinputbatch',
            name='batch_line',
        ),
        migrations.AlterField(
            model_name='trndprinputbatch',
            name='log_sheet',
            field=models.ForeignKey(
                db_column='LogSheet_id',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='dpr_input_links',
                to='transactions.trnlogsheet',
                verbose_name='Log sheet',
            ),
        ),
        migrations.AddConstraint(
            model_name='trndprinputbatch',
            constraint=models.UniqueConstraint(fields=('dpr', 'log_sheet'), name='unique_dpr_input_log_sheet'),
        ),
    ]
