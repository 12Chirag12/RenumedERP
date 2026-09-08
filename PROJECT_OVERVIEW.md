# PharmaERP Project Overview

`PharmaERP` is a Django-based ERP application for pharmaceutical laboratory operations, with modules for authentication, dashboard, master-data management, reports, and transactional workflows.

## Root files

- `manage.py`
  - Django CLI entry point for administrative tasks, migrations, custom commands, and server startup.
- `requirements.txt`
  - Python dependencies for the project.
- `README.md`
  - Project summary, setup instructions, and high-level repository layout.
- `.env`
  - Environment variable file for database connection, secret key, and runtime configuration (gitignored).


## Main Django project config

- `backend/`
  - Django project package containing core settings and root URL configuration.
  - `settings.py` - project settings, installed apps, middleware, database config, static/media settings.
  - `urls.py` - root URL router.
  - `asgi.py` / `wsgi.py` - deployment entry points.
  - `context_processors.py` - custom template context processors.
  - `request_logging.py` - request logging utilities.
  - `serve_waitress.py` - helper to run the app with Waitress.

## Application apps and features

- `users/`
  - User authentication and administration.
  - Contains models, views, forms, middleware, decorators, admin site registration, management commands, tests, and templates.
- `dashboard/`
  - Main dashboard views and templates for the application landing pages.
- `masters/`
  - Master data management for products, suppliers, BOM, machines, departments, and other reference data.
  - Contains models, views, forms, admin registration, constants, management commands, migrations, and templates.
- `reports/`
  - Reporting and export functionality.
  - Contains handlers, services, models, views, URL routes, admin registration, and report templates.
- `transactions/`
  - Business transaction models and logic.
  - Contains models, forms, views, URL routes, transaction utilities, numbering logic, tests, and templates.
- `admin_utils/`
  - Admin utility features and helper views.

## Static assets and templates

- `templates/`
  - Global shared layouts and includes.
  - `base.html`, `base_partial.html`, and reusable includes.
- `static/`
  - Source CSS, JavaScript, images, and vendor libraries.
  - Organized by feature area, including frontend assets for admin, dashboard, masters, reports, transactions, users, and vendors.
- `staticfiles/`
  - Collected static files for deployment.
- `media/`
  - Uploaded user files and generated media.
  - Includes subfolders such as `inward_documents/` and `products/`.

## Supporting directories

- `logs/`
  - Application logging files or configuration.
- `scripts/`
  - Deployment and environment scripts, including `open_firewall_for_waitress.ps1`, `production_deploy.ps1`, and `run_lan.ps1`.

## Summary

The repository follows a standard Django project layout with a dedicated `backend` config package, feature apps for users, dashboard, masters, reports, and transactions, plus separate directories for templates, static assets, media uploads, logs, and scripts.
