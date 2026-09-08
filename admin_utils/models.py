from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class DatabaseBackupSettings(models.Model):
    """
    Singleton (pk=1): periodic backup interval and status for Utilities UI + scheduler hook.
    """

    schedule_enabled = models.BooleanField(default=False)
    interval_days = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
    )
    last_successful_backup_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Database backup settings'

    def __str__(self):
        return 'Database backup settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
