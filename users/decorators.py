"""
users/decorators.py

ERP module access is enforced by users.access_middleware.ModuleAccessMiddleware
and group permissions configured in Access Control — not staff/superuser flags.

Views should use @login_required only; permissions come from the user's groups.
"""
