"""
Serve user-uploaded files from MEDIA_ROOT.

Django's ``static(MEDIA_URL, ...)`` helper only registers routes when DEBUG=True.
With DEBUG=False (LAN / Waitress), /media/ requests must be handled explicitly.
"""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET


def _safe_media_path(relative_path: str) -> Path:
    """Resolve *relative_path* under MEDIA_ROOT; reject traversal."""
    if not relative_path or relative_path.strip() != relative_path:
        raise Http404('Invalid path')
    parts = relative_path.replace('\\', '/').split('/')
    if any(p in ('', '.', '..') for p in parts):
        raise Http404('Invalid path')

    media_root = Path(settings.MEDIA_ROOT).resolve()
    full_path = (media_root.joinpath(*parts)).resolve()
    if media_root not in full_path.parents and full_path != media_root:
        raise Http404('Invalid path')
    if not full_path.is_file():
        raise Http404('File not found')
    return full_path


@login_required
@require_GET
def serve_media(request, path):
    full_path = _safe_media_path(path)
    content_type, _ = mimetypes.guess_type(str(full_path))
    return FileResponse(
        full_path.open('rb'),
        content_type=content_type or 'application/octet-stream',
        filename=full_path.name,
    )
