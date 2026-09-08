"""
Run the Django WSGI app under Waitress. Tune concurrency via environment variables.

  WAITRESS_LISTEN   Host:port (default: 0.0.0.0:8000)
  WAITRESS_THREADS  Worker threads (default: 48 — sized for ~30–35 concurrent users + burst)

Load .env from the project root (same as backend.settings) so LAN deploys match Django.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root = parent of backend/
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

from dotenv import load_dotenv

load_dotenv(_ROOT / '.env')

# Lets admin_utils start the in-process periodic DB backup scheduler (see AdminUtilsConfig.ready).
os.environ['PHARMAERP_WEB_WORKER'] = '1'

# ~30–35 simultaneous users: allow concurrent HTML + static (WhiteNoise) bursts without queueing.
_DEFAULT_WAITRESS_THREADS = 48


def main() -> None:
    listen = os.environ.get('WAITRESS_LISTEN', '0.0.0.0:8000').strip()
    raw_threads = os.environ.get('WAITRESS_THREADS', str(_DEFAULT_WAITRESS_THREADS)).strip()
    try:
        threads = max(1, int(raw_threads))
    except ValueError:
        threads = _DEFAULT_WAITRESS_THREADS

    from waitress import serve
    from backend.wsgi import application

    print(
        f'Waitress: listen={listen!r} threads={threads} '
        f'(override with WAITRESS_LISTEN / WAITRESS_THREADS)',
        flush=True,
    )
    serve(application, listen=listen, threads=threads)


if __name__ == '__main__':
    main()
