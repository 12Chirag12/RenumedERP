from django.urls import path

from . import views

urlpatterns = [
    path('reports/master-reports/', views.master_reports_page, name='master_reports'),
    path(
        'reports/api/master-reports/config/<slug>/',
        views.master_report_config,
        name='master_report_config',
    ),
    path(
        'reports/api/master-reports/options/',
        views.master_report_options,
        name='master_report_options',
    ),
    path(
        'reports/api/master-reports/data/',
        views.master_report_data,
        name='master_report_data',
    ),
    path(
        'reports/api/master-reports/export/excel/',
        views.master_report_export_excel,
        name='master_report_export_excel',
    ),
    path(
        'reports/transaction-reports/',
        views.transaction_reports_page,
        name='transaction_reports',
    ),
    path(
        'reports/api/transaction-reports/config/<slug>/',
        views.transaction_report_config,
        name='transaction_report_config',
    ),
    path(
        'reports/api/transaction-reports/options/',
        views.transaction_report_options,
        name='transaction_report_options',
    ),
    path(
        'reports/api/transaction-reports/data/',
        views.transaction_report_data,
        name='transaction_report_data',
    ),
    path(
        'reports/api/transaction-reports/export/excel/',
        views.transaction_report_export_excel,
        name='transaction_report_export_excel',
    ),
]
