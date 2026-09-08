"""
dashboard/views.py

The main dashboard view shown after login.
Displays a summary of the system and quick-access cards.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def dashboard_view(request):
    """
    Main dashboard page.
    login_required ensures only logged-in users can access this.
    The user's profile (role, name) is available via request.user.
    """
    context = {
    }
    return render(request, 'dashboard/dashboard.html', context)
