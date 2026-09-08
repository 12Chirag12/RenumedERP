from django.urls import path

from . import views

urlpatterns = [
    path('financial-years/', views.financial_year_management_view, name='admin_fy_management'),
    path('api/toggle-fy-status/', views.toggle_fy_status_api_view, name='admin_fy_toggle_status'),
    path('database-backup/', views.database_backup_view, name='admin_database_backup'),
    path('database-backup/run/', views.database_backup_run_view, name='admin_database_backup_run'),
    path('database-backup/settings/', views.database_backup_settings_view, name='admin_database_backup_settings'),
    path('database-backup/delete/', views.database_backup_delete_view, name='admin_database_backup_delete'),
    path('database-backup/download/', views.database_backup_download_view, name='admin_database_backup_download'),
]
