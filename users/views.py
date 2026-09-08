"""
users/views.py

Views for user authentication and user management.

  login_view               — Login page (accessible to everyone)
  logout_view              — Logs the user out  [POST only — C6]
  change_password_view     — Admin only: change their own password
  user_list_view           — Admin only: list all users
  create_user_view         — Admin only: create a new user
  change_user_password_view— Admin only: change a specific user's password
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_POST

from .models import UserProfile
from .forms import LoginForm, CreateUserForm, ChangePasswordForm
# ─── Login ────────────────────────────────────────────────────────────────────

def login_view(request):
    """
    Displays the split-panel login page.
    On POST: validates credentials and redirects to dashboard.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password. Please try again.')
    else:
        form = LoginForm()

    return render(request, 'users/login.html', {'form': form})


# ─── Logout ───────────────────────────────────────────────────────────────────

@require_POST
def logout_view(request):
    """
    Logs out the user and redirects to the login page.

    POST only (C6) — a plain GET /logout/ link was vulnerable to CSRF
    logout attacks where any page embedding <img src="/logout/"> would
    silently log out the visiting user.  The sidebar logout button must
    be a small <form method="POST"> with {% csrf_token %}.
    """
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


# ─── Change Own Password ──────────────────────────────────────────────────────

@login_required
def change_password_view(request):
    """
    Allows the logged-in admin (or any user with must_change_password=True,
    redirected here by ForcePasswordChangeMiddleware) to set a new password.
    After saving, logs the user out so they re-authenticate with the new one.
    """
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password'])
            request.user.save()

            # Clear the force-change flag if it is set.
            profile = getattr(request.user, 'profile', None)
            if profile and profile.must_change_password:
                profile.must_change_password = False
                profile.save()

            messages.success(
                request,
                'Password changed successfully. Please log in with your new password.',
            )
            logout(request)
            return redirect('login')
    else:
        form = ChangePasswordForm()

    return render(request, 'users/change_password.html', {'form': form})


# ─── User List ────────────────────────────────────────────────────────────────

@login_required
def user_list_view(request):
    """Shows all users in the system. Admin only."""
    users = UserProfile.objects.select_related('user').all().order_by('user__username')
    return render(request, 'users/user_list.html', {'users': users})


# ─── Create User ──────────────────────────────────────────────────────────────

@login_required
def create_user_view(request):
    """
    Admin-only page to create a new user account.

    Both the User row and the UserProfile row are written inside a single
    atomic transaction (C5) so that a failure on the second write can never
    leave an orphaned User with no profile.
    """
    if request.method == 'POST':
        form = CreateUserForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data['password'])

                role = form.cleaned_data['role']
                user.save()

                UserProfile.objects.create(
                    user=user,
                    department=form.cleaned_data['department'],
                    sub_department=form.cleaned_data['sub_department'],
                    role=role,
                    must_change_password=False,
                )

                user.groups.clear()
                role_group = form.cleaned_data.get('role_group')
                dept_group = form.cleaned_data.get('department_group')
                if role_group:
                    user.groups.add(role_group)
                if dept_group:
                    user.groups.add(dept_group)

            messages.success(request, f'User "{user.username}" created successfully.')
            return redirect('user_list')
    else:
        form = CreateUserForm()

    return render(request, 'users/create_user.html', {'form': form})


# ─── Change User Password ─────────────────────────────────────────────────────

@login_required
def change_user_password_view(request, user_id):
    """Admin-only: directly sets a new password for any user."""
    target_user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            target_user.set_password(form.cleaned_data['new_password'])
            target_user.save()

            profile = getattr(target_user, 'profile', None)
            if profile:
                profile.must_change_password = False
                profile.save()

            messages.success(
                request,
                f'Password for "{target_user.username}" has been changed successfully.',
            )
            return redirect('user_list')
    else:
        form = ChangePasswordForm()

    return render(request, 'users/change_user_password.html', {
        'form':        form,
        'target_user': target_user,
    })