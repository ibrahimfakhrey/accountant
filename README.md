# مرصود (Marsoud)

A Flask-based accounting platform for small and medium businesses in the MENA region. Arabic-first UI, Saudi VAT-compliant, with an AI accountant powered by Claude.

## Features

- **Multi-company accounting** with per-company numbering (INV-0001, JE-0001, PAYROLL-0001, EMP-0001, VB-0001 — independent per company)
- **Chart of Accounts** (Arabic-localized, auto-code generation by parent hierarchy)
- **Journal entries** with double-entry validation, pause/reactivate with audit trail, recurring schedules, templates
- **Invoices**: discounts (line + invoice level), payment methods, internal notes, PDF preview, auto reminders (7d/3d/overdue)
- **Vendor bills**: mixed line types (expense / fixed asset / inventory) in one bill, auto-creates fixed asset records
- **Fixed assets** with per-period depreciation tracking (no duplicates), vendor link, history per asset
- **Payroll** with prorated salary, variable monthly inputs (overtime/bonus/absence/late/advance), contract types, termination workflow
- **10 financial reports** (Balance Sheet, P&L, Cash Flow, P&L Compared vs prior year, Income/Expenses Summary, AR/AP Aging, VAT, Payroll, Fixed Assets) — all with PDF + Excel export
- **AI Accountant agent** (Claude) — tool use for posting journals, invoices, payments, running reports, explaining concepts
- **Email automation** (SMTP with log-only dev fallback)
- **VAT support** (KSA 15% default, configurable per company)
- **Multi-currency** (SAR, EGP, USD, EUR, AED)

## Tech Stack

- Python 3.11+ / Flask 3
- SQLAlchemy + Flask-Migrate (Alembic)
- Flask-Login for auth
- SQLite (default) — swappable via `DATABASE_URL`
- Anthropic Claude API for the AI agent

## Quick Start

```bash
git clone https://github.com/ibrahimfakhrey/accountant.git
cd accountant
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python setup.py                      # runs migrations + seeds demo data
```

`setup.py` is re-runnable — it skips work that's already done.

Then:

```bash
source .venv/bin/activate
python3 flask_app.py
```

Open http://localhost:5050 and log in with:
- **Email:** `demo@manasety.ai`
- **Password:** `demo1234`

## Manual setup (if you skip setup.sh)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # then edit to add ANTHROPIC_API_KEY etc.
FLASK_APP=flask_app.py flask db upgrade
python3 seed.py
python3 flask_app.py
```

## Schema migrations

After changing models, generate a new migration and apply:

```bash
FLASK_APP=flask_app.py flask db migrate -m "describe your change"
FLASK_APP=flask_app.py flask db upgrade
```

## Cron tick (reminders + recurring journals + overdue marking)

Add this to your system cron / scheduler to run every hour:

```bash
curl -X POST http://localhost:5050/cron/tick
```

To protect the endpoint, set `CRON_TOKEN=...` in `.env` and pass it as
`-H "X-Cron-Token: ..."` or `?token=...`.

## Project Structure

```
.
├── app/
│   ├── models/        # SQLAlchemy models (16+ models)
│   ├── routes/        # Flask blueprints
│   ├── services/      # Business logic (ledger, reports, exports, agent)
│   ├── agent/         # Claude integration + tools
│   └── templates/     # Jinja2 templates (RTL, navy/blue theme)
├── migrations/        # Alembic migration scripts
├── config.py          # Flask config
├── flask_app.py       # Entry point
├── seed.py            # Demo data seeder
├── setup.py           # First-time setup (migrations + seed)
└── requirements.txt
```

## Development Notes

- Default port: **5050** (override with `PORT` env var)
- Database file: `instance/ledgeros.db` (gitignored)
- AI agent uses Claude Sonnet 4.5 by default (configurable via `ANTHROPIC_MODEL`)
- Email service falls back to console logging if SMTP is not configured
