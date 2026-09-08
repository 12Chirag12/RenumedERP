# Replace partial unique on TrnDPR with a nullable unique column populated when batch_line
# and log_sheet are set (MySQL-compatible). Drops old partial constraint/index if present.

from django.db import migrations, models


def _drop_trndpr_old_partial_unique(apps, schema_editor):
    TrnDpr = apps.get_model('transactions', 'TrnDpr')
    table = TrnDpr._meta.db_table
    name = 'unique_dpr_batch_logsheet_machine_shift_section_dt'
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == 'mysql':
            cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
                """,
                [table, name],
            )
            if cursor.fetchone()[0]:
                cursor.execute(
                    'ALTER TABLE `%s` DROP INDEX `%s`'
                    % (table.replace('`', ''), name.replace('`', ''))
                )
        elif conn.vendor == 'postgresql':
            cursor.execute(
                'ALTER TABLE %s DROP CONSTRAINT IF EXISTS %s'
                % (
                    conn.ops.quote_name(table),
                    conn.ops.quote_name(name),
                )
            )
        elif conn.vendor == 'sqlite':
            cursor.execute('DROP INDEX IF EXISTS "%s"' % name.replace('"', ''))


def _backfill_dpr_batch_scope_keys(apps, schema_editor):
    TrnDpr = apps.get_model('transactions', 'TrnDpr')
    for row in TrnDpr.objects.filter(batch_line_id__isnull=False).iterator():
        if not row.log_sheet_id:
            continue
        dt = row.trn_dpr_dt
        date_s = dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
        key = (
            f'{row.batch_line_id}:{row.log_sheet_id}:{row.machine_id}:'
            f'{row.shift_id}:{row.section_id}:{date_s}'
        )
        TrnDpr.objects.filter(pk=row.pk).update(dpr_batch_scope_key=key)


def _clear_dpr_batch_scope_keys(apps, schema_editor):
    TrnDpr = apps.get_model('transactions', 'TrnDpr')
    TrnDpr.objects.update(dpr_batch_scope_key=None)


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0019_trninwdtl1_rate'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name='trndpr',
                    name='unique_dpr_batch_logsheet_machine_shift_section_dt',
                ),
                migrations.AddField(
                    model_name='trndpr',
                    name='dpr_batch_scope_key',
                    field=models.CharField(
                        blank=True,
                        db_column='Dpr_batch_scope_key',
                        editable=False,
                        max_length=220,
                        null=True,
                        unique=True,
                        verbose_name='Batch scope key',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_drop_trndpr_old_partial_unique, migrations.RunPython.noop),
                migrations.AddField(
                    model_name='trndpr',
                    name='dpr_batch_scope_key',
                    field=models.CharField(
                        blank=True,
                        db_column='Dpr_batch_scope_key',
                        editable=False,
                        max_length=220,
                        null=True,
                        unique=False,
                        verbose_name='Batch scope key',
                    ),
                ),
                migrations.RunPython(_backfill_dpr_batch_scope_keys, _clear_dpr_batch_scope_keys),
                migrations.AlterField(
                    model_name='trndpr',
                    name='dpr_batch_scope_key',
                    field=models.CharField(
                        blank=True,
                        db_column='Dpr_batch_scope_key',
                        editable=False,
                        max_length=220,
                        null=True,
                        unique=True,
                        verbose_name='Batch scope key',
                    ),
                ),
            ],
        ),
    ]
