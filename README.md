# Accountant (LedgerOS)

A Flask-based accounting application with Arabic/English support, built for small and medium businesses in the MENA region.

## Features

- Multi-company accounting with role-based access
- Chart of Accounts (Arabic-localized, IFRS-aligned)
- Journal entries with double-entry validation
- Invoicing, customers, and vendors
- Fixed assets and payroll
- Financial reports (Trial Balance, Income Statement, Balance Sheet)
- AI agent powered by Anthropic Claude for accounting assistance
- VAT support (KSA 15%, configurable per company)
- Multi-currency (SAR, EGP, USD, EUR, AED)

## Tech Stack

- Python 3.11+ / Flask 3
- SQLAlchemy + Flask-Migrate
- Flask-Login for auth
- SQLite (default) — swappable via `DATABASE_URL`
- Anthropic Claude API for the AI agent

## Quick Start

### 1. Clone and set up the environment

```bash
git clone https://github.com/ibrahimfakhrey/accountant.git
cd accountant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set:

- `FLASK_SECRET_KEY` — any long random string
- `ANTHROPIC_API_KEY` — from https://console.anthropic.com/ (only needed for the AI agent)
- `DATABASE_URL` — defaults to local SQLite, fine for dev

### 3. Seed demo data

```bash
python seed.py
```

This creates a demo user and company:

- **Email:** `demo@manasety.ai`
- **Password:** `demo1234`
- **Company:** شركة الأمل التجارية (SAR, 15% VAT)
- Chart of Accounts: 38 accounts
- 3 customers, 3 vendors, 3 employees

### 4. Run the server

```bash
python flask_app.py
```

Open http://localhost:5050 and log in with the demo credentials.

## Project Structure

```
.
├── app/
│   ├── models/        # SQLAlchemy models
│   ├── routes/        # Flask blueprints (auth, dashboard, invoices, etc.)
│   ├── services/      # Business logic (seed_coa, reports, agent tools)
│   ├── templates/     # Jinja2 templates
│   └── static/        # CSS, JS, assets
├── config.py          # Flask config
├── flask_app.py       # Entry point
├── seed.py            # Demo data seeder
└── requirements.txt
```

## Development Notes

- Default port: **5050** (override with `PORT` env var)
- Database file: `instance/ledgeros.db` (gitignored)
- Migrations: `flask db migrate -m "msg"` / `flask db upgrade`
