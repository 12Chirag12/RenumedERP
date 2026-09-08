"""
Structured request logging: authenticated user (not only IP), slow requests, 5xx responses.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger('pharmaerp.request')

# Milliseconds; 0 disables slow-request logging.
_SLOW_MS_DEFAULT = 2000


class RequestContextLoggingMiddleware:
    """
    After AuthenticationMiddleware: log method, path, status, duration, client IP,
    and username when authenticated. Logs WARNING for 5xx and for responses slower
    than SLOW_REQUEST_MS (default 2000).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        slow_ms = getattr(settings, 'SLOW_REQUEST_MS', _SLOW_MS_DEFAULT)
        try:
            slow_ms = int(slow_ms)
        except (TypeError, ValueError):
            slow_ms = _SLOW_MS_DEFAULT

        start = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            u = getattr(request, 'user', None)
            if u is not None and getattr(u, 'is_authenticated', False):
                uid = getattr(u, 'pk', None)
                uname = getattr(u, 'get_username', lambda: '')()
                user_part = f'user_id={uid} username={uname!r}'
            else:
                user_part = 'anonymous'
            logger.exception(
                f'{request.method} {request.path} ERROR after {elapsed_ms:.1f}ms {user_part}'
            )
            raise
        elapsed_ms = (time.monotonic() - start) * 1000.0

        user_part = 'anonymous'
        u = getattr(request, 'user', None)
        if u is not None and getattr(u, 'is_authenticated', False):
            uid = getattr(u, 'pk', None)
            uname = getattr(u, 'get_username', lambda: '')()
            user_part = f'user_id={uid} username={uname!r}'

        # Prefer proxy-forwarded client when USE_TLS / reverse proxy (django sets META)
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            client_ip = xff.split(',')[0].strip()
        else:
            client_ip = request.META.get('REMOTE_ADDR', '')

        status = getattr(response, 'status_code', None)
        extra = {
            'method': request.method,
            'path': request.path,
            'status_code': status,
            'duration_ms': round(elapsed_ms, 2),
            'client_ip': client_ip,
            'user_part': user_part,
        }

        msg = (
            f'{request.method} {request.path} status={status} '
            f'{elapsed_ms:.1f}ms ip={client_ip} {user_part}'
        )

        if status is not None and status >= 500:
            logger.error(msg, extra=extra)
        elif slow_ms > 0 and elapsed_ms >= slow_ms:
            logger.warning(f'SLOW {msg}', extra=extra)
        else:
            logger.info(msg, extra=extra)

        return response
