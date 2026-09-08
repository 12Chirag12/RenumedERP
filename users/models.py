"""
users/models.py

Extends Django's built-in User model with a UserProfile.
Each user has a department, sub-department, role, and a flag
to force a password change on first login.
"""

from django.db import models
from django.contrib.auth.models import Group, User


class AccessModule(models.Model):
    """Anchor model so module permissions are stored under the users app."""

    slug = models.CharField(max_length=64, primary_key=True, default='erp')

    class Meta:
        verbose_name = 'ERP access module'
        verbose_name_plural = 'ERP access modules'
        default_permissions = ()


class AccessGroupMeta(models.Model):
    """Marks a Django Group as role-based or department-based."""

    GROUP_TYPE_ROLE = 'role'
    GROUP_TYPE_DEPARTMENT = 'department'
    GROUP_TYPE_CHOICES = (
        (GROUP_TYPE_ROLE, 'Role-based'),
        (GROUP_TYPE_DEPARTMENT, 'Department-based'),
    )

    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name='access_meta',
    )
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES)

    class Meta:
        verbose_name = 'Access group metadata'
        verbose_name_plural = 'Access group metadata'

    def __str__(self):
        return f'{self.group.name} ({self.get_group_type_display()})'


class UserProfile(models.Model):
    """
    Extra information linked to each Django User.
    Created automatically when Admin creates a new user.
    """

    # One-to-one link to Django's built-in User model
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,   # Delete profile if user is deleted
        related_name='profile'
    )

    # The department this user belongs to
    department = models.CharField(max_length=100, blank=True, default='')

    # The sub-department within the main department
    sub_department = models.CharField(max_length=100, blank=True, default='')

    # The user's specific role/job title
    role = models.CharField(max_length=100, default='')

    # Forces the user to change their password on first login
    must_change_password = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def full_name(self):
        """Returns the user's full name, or username if not set."""
        name = self.user.get_full_name()
        return name if name.strip() else self.user.username
