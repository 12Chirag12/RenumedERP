from django.db import migrations, models


def copy_legacy_operators(apps, schema_editor):
    TrnDpr = apps.get_model('transactions', 'TrnDpr')
    through = TrnDpr.operators.through
    rows = []
    for dpr in TrnDpr.objects.only('trn_dpr_id', 'operator1_id', 'operator2_id').iterator():
        seen = set()
        for operator_id in (dpr.operator1_id, dpr.operator2_id):
            if operator_id and operator_id not in seen:
                rows.append(through(trndpr_id=dpr.pk, mstoperator_id=operator_id))
                seen.add(operator_id)
    if rows:
        through.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0026_alter_trninwhed_vehicle_no'),
    ]

    operations = [
        migrations.AddField(
            model_name='trndpr',
            name='operators',
            field=models.ManyToManyField(
                blank=True,
                related_name='dpr_entries',
                to='masters.mstoperator',
                verbose_name='Operators',
            ),
        ),
        migrations.RunPython(copy_legacy_operators, migrations.RunPython.noop),
    ]