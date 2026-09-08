import django.core.validators
from django.db import migrations, models


def hours_to_days(apps, schema_editor):
    DatabaseBackupSettings = apps.get_model('admin_utils', 'DatabaseBackupSettings')
    for row in DatabaseBackupSettings.objects.all():
        try:
            h = int(row.interval_hours)
        except (TypeError, ValueError):
            h = 24
        days = max(1, min(90, (h + 23) // 24))
        row.interval_days = days
        row.save(update_fields=['interval_days'])


class Migration(migrations.Migration):

    dependencies = [
        ('admin_utils', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='databasebackupsettings',
            name='interval_days',
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(90),
                ],
            ),
        ),
        migrations.RunPython(hours_to_days, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='databasebackupsettings',
            name='interval_hours',
        ),
    ]
