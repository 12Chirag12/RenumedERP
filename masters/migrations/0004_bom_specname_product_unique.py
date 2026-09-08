from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('masters', '0003_mstbom_batch_size_batch_nos'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mstbomrmhed',
            name='spec_name',
            field=models.CharField(max_length=300, verbose_name='Specification Name'),
        ),
        migrations.AlterField(
            model_name='mstbompmhed',
            name='spec_name',
            field=models.CharField(max_length=300, verbose_name='Specification Name'),
        ),
        migrations.AddConstraint(
            model_name='mstbomrmhed',
            constraint=models.UniqueConstraint(
                fields=('spec_name', 'product'),
                name='unique_bom_rm_specname_product',
            ),
        ),
        migrations.AddConstraint(
            model_name='mstbompmhed',
            constraint=models.UniqueConstraint(
                fields=('spec_name', 'product'),
                name='unique_bom_pm_specname_product',
            ),
        ),
    ]

