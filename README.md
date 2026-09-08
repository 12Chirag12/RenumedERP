# PharmaERP

Web-based ERP for pharmaceutical laboratory operations: authentication, dashboard, and master-data management (products, items, customers, BOM, logistics, and related reference data).

**Stack:** Python · [Django](https://www.djangoproject.com/) 6.x · MySQL 8 (utf8mb4) · [Pillow](https://python-pillow.org/) (uploads) · [python-dotenv](https://github.com/theskumar/python-dotenv) (configuration)

---

## Repository layout

```
PharmaERP/
├── backend/           # Project settings, root URLs, WSGI/ASGI, context processors
├── users/             # Login, logout, profiles, admin user management, forced password change
├── dashboard/         # Main dashboard
├── masters/           # Master data (sections, machines, UOM, products, items, customers, BOM, …)
├── templates/         # Shared layouts (navbar, sidebar)
├── static/            # CSS, JavaScript, images
├── media/             # User uploads (gitignored; created at runtime)
├── manage.py
├── .env.example       # All supported environment variables (copy to `.env`)
└── requirements.txt
```

---

## Prerequisites

- Python 3.12+ (compatible with Django 6)
- MySQL Server with a database you can connect to (local or remote)
- On Windows, MySQL client build tools may be required for `mysqlclient`; use a prebuilt wheel or install [MySQL Connector/C](https://dev.mysql.com/downloads/c-api/) as needed.

---

## Quick start (development)

### 1. Clone and virtual environment

```bash
cd PharmaERP
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment variables

Copy `.env.example` to `.env` in the project root and edit values for your machine. The example file lists every variable the codebase reads, with comments.

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `DB_NAME` | Yes* | MySQL database name |
| `DB_USER` | Yes* | MySQL user |
| `DB_PASSWORD` | Yes* | MySQL password |
| `DB_HOST` | Yes* | Host (e.g. `127.0.0.1`) |
| `DB_PORT` | Yes* | Port (e.g. `3306`) |
| `SECRET_KEY` | Prod | Django secret key; **required** when `DEBUG=False` (must not use dev default) |
| `DEBUG` | No | `True` or `False` (defaults to `True` if omitted) |
| `ALLOWED_HOSTS` | Prod | Comma-separated hostnames (required when `DEBUG=False`; never use `*` in production) |
| `CSRF_TRUSTED_ORIGINS` | Prod | Comma-separated full origins for LAN/HTTPS (required when `DEBUG=False`) |
| `USE_TLS` | No | `True` if HTTPS is terminated at a reverse proxy |
| `SECURE_SSL_REDIRECT` | No | When `USE_TLS=True`, defaults `True`; set `False` if the proxy handles HTTP→HTTPS |
| `SESSION_COOKIE_SAMESITE` | No | `Lax` (default), `Strict`, or `None` |
| `DB_CONN_MAX_AGE` | No | DB connection reuse in seconds (default `60`) |
| `SLOW_REQUEST_MS` | No | Log requests slower than this many ms at WARNING (default `2000`; `0` = off) |
| `REPORT_COMPANY_HEADER` | No | Company line for printed/PDF reports (built-in default if unset) |
| `DATABASE_BACKUP_DIR` | No | Absolute folder for MySQL dumps; default `database_backups/` under project root; `~` allowed |
| `DATABASE_BACKUP_RETENTION` | No | How many newest backup files to keep (default `30`) |
| `MYSQLDUMP_PATH` | No | Full path to `mysqldump` / `mysqldump.exe` if not on `PATH` |
| `DATABASE_BACKUP_FILE_PREFIX` | No | Backup filename prefix (default `pharmaerp_`) |
| `WAITRESS_LISTEN` | No | Host:port for `serve_waitress.py` (default `0.0.0.0:8000`) |
| `WAITRESS_THREADS` | No | Waitress worker threads (default `48` in `serve_waitress.py`) |

\*Required for normal operation: Django expects these MySQL settings; leave none empty in real deployments.

Example (adjust values):

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
DB_NAME=pharma_erp
DB_USER=root
DB_PASSWORD=yourpassword
DB_HOST=127.0.0.1
DB_PORT=3306

# Optional: store DB dumps outside the project tree (admin Utilities + manage.py backup commands)
# DATABASE_BACKUP_DIR=D:/Backups/PharmaERP
```

Create the MySQL database before migrating, e.g. `CREATE DATABASE pharma_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`.

### 4. Migrate and seed reference data

```bash
python manage.py migrate
python manage.py seed_departments
```

`seed_departments` is idempotent: it adds base departments and skips rows that already exist.

### 5. Create the first administrator

```bash
python manage.py create_admin
```

Defaults: username `admin`, password `Admin@1234`. Override with flags, e.g.:

```bash
python manage.py create_admin --username admin --password YourSecurePassword --email admin@example.com
```

### 6. Run the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) — the site redirects to the login page.

---

## Default login (after `create_admin` with defaults)

| Field    | Value      |
|----------|------------|
| Username | `admin`    |
| Password | `Admin@1234` |

Change the password after first login in production.

---

## Database backups

PharmaERP uses **MySQL logical backups** via the `mysqldump` client (install **MySQL Shell / client tools** on the app server so `mysqldump` is available, or set `MYSQLDUMP_PATH` in `.env`).

- **Utilities (admin users):** Sidebar → **Utilities** → **Database backup** — configure the schedule, run a backup on demand, download or delete files. Dumps are stored under `DATABASE_BACKUP_DIR` (default `database_backups/`, gitignored) as gzip `.sql.gz` files; old files beyond the retention count are removed automatically.
- **Ad hoc CLI:** `python manage.py backup_database`
- **Periodic runs:** In Utilities, enable **periodic backups** and set the interval in **days** (1–90). Schedule **`python manage.py run_scheduled_backup`** with Windows Task Scheduler or **cron** (for example **once daily**). The command exits quietly until the configured number of days has passed since the last successful backup.

---

## Main features

- **Authentication:** Login / logout; optional forced password change for new users (`ForcePasswordChangeMiddleware`).
- **Users (admin):** List users, create users, reset passwords; role stored on `UserProfile`.
- **Utilities (admin):** Financial year controls; **Database backup** (MySQL dumps, schedule + Task Scheduler / cron hook).
- **Dashboard:** Entry hub after login.
- **Masters:** CRUD-style screens for reference and transactional master data, including:
  - Section, machine (with department linkage), UOM  
  - Product attributes (capsule size/color, etc.)  
  - Logistics (transporter, state)  
  - Production stage, item type, packing style, expenses  
  - Product, item, customer (with product links)  
  - BOM (raw material / packaging) with supporting AJAX endpoints  

Django’s built-in admin is available at `/admin/` for superusers.

---

## Production notes

- Set `DEBUG=False`, a strong `SECRET_KEY`, and explicit `ALLOWED_HOSTS`.
- Set `CSRF_TRUSTED_ORIGINS` to every URL origin clients use (with scheme), e.g. `http://192.168.1.10` and `http://erp-servername` if both work.
- Run `python manage.py collectstatic` and serve `STATIC_ROOT` with your web server or platform.
- Use a proper database user with least privilege; keep backups and TLS to MySQL if remote.

### LAN deployment (single server, clients on the same network)

Typical pattern: one **server PC** runs MySQL (or MySQL on the same host), the Django app behind a production WSGI server, and optionally **nginx** or **IIS** as reverse proxy on port 80/443. Clients open `http://<server-ip>` or `http://<hostname>`.

1. **Server preparation:** Install Python, MySQL, create DB and user; clone/copy the project; create `.env` with `DEBUG=False`, strong `SECRET_KEY`, `ALLOWED_HOSTS` = server hostname + LAN IP (no `*`), and `CSRF_TRUSTED_ORIGINS` matching how users type the URL (include port if not 80), e.g. `http://192.168.1.50,http://pharma-erp`.
2. **Dependencies:** `pip install -r requirements.txt` (includes **waitress** on Windows; use **gunicorn** on Linux if you prefer).
3. **Django:** `migrate`, `seed_departments`, `create_admin`, `collectstatic`.
4. **Run the app:** `python run_waitress.py` (listens on `0.0.0.0:8000` with **8 threads** by default). Waitress’s default of 4 threads is below typical browser concurrency (~6 connections), which causes harmless but noisy “Task queue depth” warnings—increase capacity with `python run_waitress.py --threads 12` or set `WAITRESS_THREADS=12` in `.env`. For a busy LAN, try 12–16 threads (or more if the host has CPU headroom).
5. **Process manager / service:** On Windows, run at startup via **Task Scheduler** or as a **Windows service**; on Linux use **systemd**, so the app restarts on boot.
6. **Reverse proxy (recommended):** Terminate HTTP/HTTPS at nginx/IIS, forward to `127.0.0.1:8000` (or your WSGI port). If you use HTTPS, set `USE_TLS=True` and configure the proxy to send `X-Forwarded-Proto: https`.
7. **Firewall:** Allow inbound **only** from the LAN subnet (or AD-defined ranges) on 80/443 (and block WAN). MySQL port **3306** should not be exposed to clients—only localhost or the app host.
8. **Backups:** Use **Utilities → Database backup** plus `run_scheduled_backup` (see **Database backups** above). Also back up the `media/` folder and keep copies off the server PC.
9. **Monitoring:** Disk space for uploads and logs; optional Windows Event Log / file logging for Django.
