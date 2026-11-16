from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/director/', views.director_dashboard_view, name='director_dashboard'),
    path('dashboard/api/summary-kpis/', views.api_summary_kpis, name='dashboard_summary_kpis'),
    path('dashboard/api/inward-logsheet/', views.api_inward_logsheet, name='dashboard_inward_logsheet'),
    path('dashboard/api/granulation-logsheet/', views.api_granulation_logsheet, name='dashboard_granulation_logsheet'),
    path('dashboard/api/dpr-report/', views.api_dpr_report, name='dashboard_dpr_report'),
    path('dashboard/api/rm-dispensing/', views.api_rm_dispensing, name='dashboard_rm_dispensing'),
    path('dashboard/api/packing-report/', views.api_packing_report, name='dashboard_packing_report'),
    path('dashboard/api/sales-orders/', views.api_sales_orders, name='dashboard_sales_orders'),
    path('dashboard/api/sales-summary/', views.api_sales_summary, name='dashboard_sales_summary'),
    path('dashboard/api/stock-overview/', views.api_stock_overview, name='dashboard_stock_overview'),
]
