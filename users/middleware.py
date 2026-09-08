"""
users/middleware.py

ForcePasswordChangeMiddleware
──────────────────────────────
Intercepts every request from an authenticated user and redirects to
/change-password/ if their profile's must_change_password flag is True.

The user cannot navigate anywhere else until they set a new password.

Add to settings.py MIDDLEWARE list, after AuthenticationMiddleware:

    MIDDLEWARE = [
        ...
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'users.middleware.ForcePasswordChangeMiddleware',   # ← add here
        ...
    ]

Exempt URLs (the user must be able to reach these without a redirect):
    /change-password/   — the form they need to submit
    /logout/            — they should be able to log out
    /login/             — in case session expires mid-flow
"""

from django.shortcuts import redirect
from django.urls import reverse


# URLs that are always accessible regardless of must_change_password.
# Stored as a set for O(1) lookup on every request.
_EXEMPT_URL_NAMES = {'change_password', 'logout', 'login'}


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Resolve exempt paths once at startup so we never reverse() per request.
        self._exempt_paths = None

    def _get_exempt_paths(self):
        """Lazy-resolve exempt paths the first time they are needed."""
        if self._exempt_paths is None:
            self._exempt_paths = {reverse(name) for name in _EXEMPT_URL_NAMES}
        return self._exempt_paths

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.path not in self._get_exempt_paths()
        ):
            profile = getattr(request.user, 'profile', None)
            if profile and profile.must_change_password:
                return redirect('change_password')

        return self.get_response(request)