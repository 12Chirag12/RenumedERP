from django.contrib import admin

from .models import AccessGroupMeta, AccessModule, UserProfile


@admin.register(AccessModule)
class AccessModuleAdmin(admin.ModelAdmin):
    list_display = ['slug']


@admin.register(AccessGroupMeta)
class AccessGroupMetaAdmin(admin.ModelAdmin):
    list_display = ['group', 'group_type']
    list_filter = ['group_type']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'must_change_password']
    list_filter = ['role']
