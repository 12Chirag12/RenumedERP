"""
Enforce module permissions from access_registry.URL_PERMISSION_MAP.
Views keep @login_required; this layer checks group permissions in one place.
"""

from django.contrib import messages
from django.shortcuts import redirect

from .access import user_has_access
from .access_registry import EXEMPT_URL_NAMES, URL_PERMISSION_MAP


class ModuleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            match = request.resolver_match
            if match and match.url_name:
                if match.url_name not in EXEMPT_URL_NAMES:
                    ns = match.namespace
                    key = f'{ns}:{match.url_name}' if ns else match.url_name
                    module_codename = URL_PERMISSION_MAP.get(key) or URL_PERMISSION_MAP.get(
                        match.url_name
                    )
                    if module_codename and not user_has_access(request.user, module_codename):
                        messages.error(request, 'Access denied.')
                        return redirect('dashboard')
        return self.get_response(request)
