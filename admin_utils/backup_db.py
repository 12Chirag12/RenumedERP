"""
MySQL logical backups via mysqldump. Used by management commands and Utilities views.

Requires MySQL client tools (mysqldump) on the server PATH, or MYSQLDUMP_PATH in settings / env.
"""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone


class BackupError(Exception):
    """User-visible backup failure (missing tools, mysqldump error, etc.)."""


def _backup_dir() -> Path:
    d = getattr(settings, 'DATABASE_BACKUP_DIR', None)
    if d is None:
        raise BackupError('DATABASE_BACKUP_DIR is not configured.')
    return Path(d)


def _retention_count() -> int:
    try:
        n = int(getattr(settings, 'DATABASE_BACKUP_RETENTION', 30))
    except (TypeError, ValueError):
        n = 30
    return max(1, min(n, 500))


def _resolve_mysqldump() -> str:
    explicit = getattr(settings, 'MYSQLDUMP_PATH', None) or os.environ.get('MYSQLDUMP_PATH')
    if explicit:
        p = str(explicit).strip()
        if p:
            if Path(p).is_file():
                return p
            raise BackupError(f'MYSQLDUMP_PATH is set but file not found: {p}')
    w = shutil.which('mysqldump')
    if not w:
        raise BackupError(
            'mysqldump was not found. Install MySQL client tools, add them to PATH, '
            'or set MYSQLDUMP_PATH in .env to the full path of mysqldump.exe.'
        )
    return w


def _db_config() -> dict:
    db = settings.DATABASES.get('default') or {}
    name = db.get('NAME') or ''
    user = db.get('USER') or ''
    password = db.get('PASSWORD') or ''
    host = db.get('HOST') or '127.0.0.1'
    port = str(db.get('PORT') or '3306')
    if not name:
        raise BackupError('Database NAME is not configured.')
    if not user:
        raise BackupError('Database USER is not configured.')
    return {'NAME': name, 'USER': user, 'PASSWORD': password, 'HOST': host, 'PORT': port}


def _write_client_cnf(cfg: dict) -> str:
    fd, path = tempfile.mkstemp(prefix='pharmaerp_mysqldump_', suffix='.cnf', text=False)
    try:
        body = (
            '[client]\n'
            f'user={cfg["USER"]}\n'
            f'password={cfg["PASSWORD"]}\n'
            f'host={cfg["HOST"]}\n'
            f'port={cfg["PORT"]}\n'
        )
        os.write(fd, body.encode('utf-8'))
    finally:
        os.close(fd)
    if os.name != 'nt':
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def list_backup_files() -> list[dict]:
    """Newest first. Each dict: name, size, mtime (datetime)."""
    root = _backup_dir()
    if not root.is_dir():
        return []
    prefix = getattr(settings, 'DATABASE_BACKUP_FILE_PREFIX', 'pharmaerp_')
    out: list[tuple[Path, float]] = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        n = p.name
        if not n.startswith(prefix):
            continue
        if not (n.endswith('.sql') or n.endswith('.sql.gz')):
            continue
        try:
            out.append((p, p.stat().st_mtime))
        except OSError:
            continue
    out.sort(key=lambda t: t[1], reverse=True)
    result = []
    for p, mtime in out:
        try:
            st = p.stat()
            sz = st.st_size
            if sz < 1024:
                size_display = f'{sz} B'
            elif sz < 1024 * 1024:
                size_display = f'{sz / 1024:.1f} KB'
            elif sz < 1024 * 1024 * 1024:
                size_display = f'{sz / (1024 * 1024):.1f} MB'
            else:
                size_display = f'{sz / (1024 * 1024 * 1024):.1f} GB'
            result.append(
                {
                    'name': p.name,
                    'size': sz,
                    'size_display': size_display,
                    'mtime': datetime.fromtimestamp(st.st_mtime, tz=timezone.get_current_timezone()),
                }
            )
        except OSError:
            continue
    return result


def prune_old_backups() -> None:
    root = _backup_dir()
    if not root.is_dir():
        return
    prefix = getattr(settings, 'DATABASE_BACKUP_FILE_PREFIX', 'pharmaerp_')
    keep = _retention_count()
    eligible = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        n = p.name
        if not n.startswith(prefix):
            continue
        if not (n.endswith('.sql') or n.endswith('.sql.gz')):
            continue
        eligible.append(p)
    paths = sorted(eligible, key=lambda p: p.stat().st_mtime, reverse=True)
    for p in paths[keep:]:
        try:
            p.unlink()
        except OSError:
            pass


def _safe_backup_basename(name: str) -> bool:
    if '/' in name or '\\' in name or name in ('.', '..'):
        return False
    prefix = getattr(settings, 'DATABASE_BACKUP_FILE_PREFIX', 'pharmaerp_')
    if not name.startswith(prefix):
        return False
    return name.endswith('.sql') or name.endswith('.sql.gz')


def delete_backup_file(name: str) -> None:
    if not _safe_backup_basename(name):
        raise BackupError('Invalid backup file name.')
    root = _backup_dir().resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise BackupError('Invalid path.') from None
    if not path.is_file():
        raise BackupError('File not found.')
    path.unlink()


def resolve_download_path(name: str) -> Path:
    if not _safe_backup_basename(name):
        raise BackupError('Invalid backup file name.')
    root = _backup_dir().resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise BackupError('Invalid path.') from None
    if not path.is_file():
        raise BackupError('File not found.')
    return path


def run_mysql_backup(*, gzip_output: bool = True, track_in_settings: bool = True) -> Path:
    """
    Run mysqldump for the default database. Updates DatabaseBackupSettings on success/failure
    when track_in_settings is True.
    """
    from admin_utils.models import DatabaseBackupSettings

    cfg = _db_config()
    mysqldump = _resolve_mysqldump()
    backup_root = _backup_dir()
    backup_root.mkdir(parents=True, exist_ok=True)

    prefix = getattr(settings, 'DATABASE_BACKUP_FILE_PREFIX', 'pharmaerp_')
    stamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')
    ext = '.sql.gz' if gzip_output else '.sql'
    out_name = f'{prefix}{cfg["NAME"]}_{stamp}{ext}'
    out_path = backup_root / out_name

    cnf_path = _write_client_cnf(cfg)
    try:
        cmd = [
            mysqldump,
            f'--defaults-extra-file={cnf_path}',
            '--single-transaction',
            '--routines',
            '--triggers',
            '--set-gtid-purged=OFF',
            '--default-character-set=utf8mb4',
            '--column-statistics=0',
            cfg['NAME'],
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdout is not None
        try:
            if gzip_output:
                with gzip.open(out_path, 'wb', compresslevel=6) as gz:
                    while True:
                        chunk = proc.stdout.read(1024 * 1024)
                        if not chunk:
                            break
                        gz.write(chunk)
            else:
                with open(out_path, 'wb') as raw:
                    while True:
                        chunk = proc.stdout.read(1024 * 1024)
                        if not chunk:
                            break
                        raw.write(chunk)
        finally:
            proc.stdout.close()

        code = proc.wait()
        stderr_b = proc.stderr.read() if proc.stderr else b''
        if code != 0:
            try:
                if out_path.exists():
                    out_path.unlink()
            except OSError:
                pass
            err = stderr_b.decode('utf-8', errors='replace').strip() or f'exit code {code}'
            msg = f'mysqldump failed: {err}'
            if track_in_settings:
                s = DatabaseBackupSettings.load()
                s.last_error = msg[:2000]
                s.save(update_fields=['last_error'])
            raise BackupError(msg)

    finally:
        try:
            os.unlink(cnf_path)
        except OSError:
            pass

    prune_old_backups()

    if track_in_settings:
        s = DatabaseBackupSettings.load()
        s.last_successful_backup_at = timezone.now()
        s.last_error = ''
        s.save(update_fields=['last_successful_backup_at', 'last_error'])

    return out_path
