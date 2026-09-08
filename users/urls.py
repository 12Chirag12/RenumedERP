"""
users/urls.py

URL routes for the Users app:
  /login/                          → Login page
  /logout/                         → Logout
  /users/                          → Admin: list all users
  /users/create/                   → Admin: create new user
  /users/change-password/<id>/     → Admin: change a user's password
  /change-password/                → Admin only: change own password
"""

from django.urls import path
from . import views
from . import access_views

urlpatterns = [
    # Authentication
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),

    # Change password (Admin only — own password)
    path('change-password/', views.change_password_view, name='change_password'),

    # User Management (Admin Only)
    path('users/',                              views.user_list_view,           name='user_list'),
    path('users/create/',                       views.create_user_view,         name='create_user'),
    path('users/change-password/<int:user_id>/', views.change_user_password_view, name='change_user_password'),

    path('utilities/access-control/', access_views.access_control_view, name='access_control'),
    path('utilities/access-control/save/', access_views.access_control_save_view, name='access_control_save'),
]
