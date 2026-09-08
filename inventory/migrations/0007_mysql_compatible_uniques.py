# MySQL cannot apply partial UniqueConstraint; replace with full uniques on (header, product)
# and (header, item). Multiple NULLs in a nullable FK column are allowed, so behaviour matches
# the old partial rules. Drops old indexes/constraints only if they exist (MySQL may have none).

from django.db import migrations, models


def _drop_trnstkadjdtl1_old_uniques(apps, schema_editor):
    TrnStkAdjDtl1 = apps.get_model('inventory', 'TrnStkAdjDtl1')
    table = TrnStkAdjDtl1._meta.db_table
    names = ('uniq_stk_adj_hed_product', 'uniq_stk_adj_hed_item')
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == 'mysql':
            for name in names:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.statistics
                    WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
                    """,
                    [table, name],
                )
                if cursor.fetchone()[0]:
                    cursor.execute(
                        'ALTER TABLE `%s` DROP INDEX `%s`' % (table.replace('`', ''), name.replace('`', ''))
                    )
        elif conn.vendor == 'postgresql':
            for name in names:
                cursor.execute(
                    'ALTER TABLE %s DROP CONSTRAINT IF EXISTS %s'
                    % (
                        conn.ops.quote_name(table),
                        conn.ops.quote_name(name),
                    )
                )
        elif conn.vendor == 'sqlite':
            for name in names:
                cursor.execute('DROP INDEX IF EXISTS "%s"' % name.replace('"', ''))


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_alter_inventorystock_is_closed'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name='trnstkadjdtl1',
                    name='uniq_stk_adj_hed_product',
                ),
                migrations.RemoveConstraint(
                    model_name='trnstkadjdtl1',
                    name='uniq_stk_adj_hed_item',
                ),
                migrations.AddConstraint(
                    model_name='trnstkadjdtl1',
                    constraint=models.UniqueConstraint(
                        fields=('header', 'product'),
                        name='uniq_stk_adj_hed_product',
                    ),
                ),
                migrations.AddConstraint(
                    model_name='trnstkadjdtl1',
                    constraint=models.UniqueConstraint(
                        fields=('header', 'item'),
                        name='uniq_stk_adj_hed_item',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_drop_trnstkadjdtl1_old_uniques, migrations.RunPython.noop),
                migrations.AddConstraint(
                    model_name='trnstkadjdtl1',
                    constraint=models.UniqueConstraint(
                        fields=('header', 'product'),
                        name='uniq_stk_adj_hed_product',
                    ),
                ),
                migrations.AddConstraint(
                    model_name='trnstkadjdtl1',
                    constraint=models.UniqueConstraint(
                        fields=('header', 'item'),
                        name='uniq_stk_adj_hed_item',
                    ),
                ),
            ],
        ),
    ]
