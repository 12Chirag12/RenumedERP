from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('masters', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mstsupplier',
            name='short_name',
            field=models.CharField(
                max_length=10,
                unique=True,
                blank=True,
                null=True,
                verbose_name='Short Name',
            ),
        ),
    ]

