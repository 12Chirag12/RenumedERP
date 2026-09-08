"""
Main URL configuration for PharmaERP.

URL structure:
  /           → Redirects to login
  /login/     → Login page
  /logout/    → Logout
  /dashboard/ → Main dashboard
  /users/     → User management (admin only)
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

from backend.media_views import serve_media

urlpatterns = [
    # Admin utilities (must be before Django admin's `admin/` catch-all)
    path('admin/utilities/', include('admin_utils.urls')),
    
    # Django's built-in admin panel (for superuser access)
    path('admin/', admin.site.urls),

    # Redirect root URL to the login page
    path('', lambda request: redirect('login'), name='home'),

    # User authentication & management routes
    path('', include('users.urls')),

    # Dashboard routes
    path('', include('dashboard.urls')),

    # Masters routes (Section, Machines, etc.)
    path('', include('masters.urls')),

    # Transactions (Inward, etc.)
    path('', include('transactions.urls')),

    # Reports (master reports module, etc.)
    path('', include('reports.urls')),

    # Inventory (customer monthly stock, etc.)
    path('', include('inventory.urls')),

    # User uploads — always served here (static() is a no-op when DEBUG=False).
    re_path(r'^media/(?P<path>.+)$', serve_media, name='serve_media'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)