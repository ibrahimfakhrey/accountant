"""sync legacy db to full schema

Idempotent migration that brings a legacy database (created from the old
initial commit before all the recent module additions) up to the current
model state. Safe to run on:
  - A fresh DB that already has the full initial_schema migration applied
    (no-op)
  - A legacy DB from eb10069 era (adds all missing tables and columns)
  - Any partial state in between

It checks the live DB schema with the inspector before each ADD COLUMN
or CREATE TABLE, so re-running is harmless.

Revision ID: 6e0cd4a49d23
Revises: 51e8090300d1
Create Date: 2026-05-25 23:54:05
"""
from alembic import op
import sqlalchemy as sa


revision = '6e0cd4a49d23'
down_revision = '51e8090300d1'
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name):
    return name in _inspector().get_table_names()


def _has_column(table, col):
    if not _has_table(table):
        return False
    return col in [c["name"] for c in _inspector().get_columns(table)]


def _add_col(table, col_name, col_type, **kwargs):
    if _has_column(table, col_name):
        return
    op.add_column(table, sa.Column(col_name, col_type, **kwargs))


def upgrade():
    # ─── New tables (the modules added recently) ───────────────────────
    if not _has_table("number_sequences"):
        op.create_table(
            "number_sequences",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("doc_type", sa.String(20), nullable=False),
            sa.Column("next_number", sa.Integer, nullable=False, default=1),
            sa.UniqueConstraint("company_id", "doc_type", name="uq_sequence_company_type"),
        )

    if not _has_table("products"):
        op.create_table(
            "products",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("default_price", sa.Numeric(15, 4), default=0),
            sa.Column("default_tax_rate", sa.Numeric(5, 2)),
            sa.Column("sku", sa.String(50)),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("created_at", sa.DateTime),
        )

    if not _has_table("payment_methods"):
        op.create_table(
            "payment_methods",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("name", sa.String(50), nullable=False),
            sa.Column("name_ar", sa.String(50)),
            sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("is_default", sa.Boolean, default=False),
            sa.UniqueConstraint("company_id", "name", name="uq_pm_company_name"),
        )

    if not _has_table("journal_audits"):
        op.create_table(
            "journal_audits",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("entry_id", sa.Integer, sa.ForeignKey("journal_entries.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
            sa.Column("action", sa.String(20), nullable=False),
            sa.Column("reason", sa.Text),
            sa.Column("created_at", sa.DateTime, index=True),
        )

    if not _has_table("journal_templates"):
        op.create_table(
            "journal_templates",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("created_at", sa.DateTime),
        )

    if not _has_table("journal_template_lines"):
        op.create_table(
            "journal_template_lines",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("template_id", sa.Integer, sa.ForeignKey("journal_templates.id"), nullable=False),
            sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
            sa.Column("debit", sa.Numeric(15, 4), default=0),
            sa.Column("credit", sa.Numeric(15, 4), default=0),
            sa.Column("memo", sa.Text),
        )

    if not _has_table("recurring_journals"):
        op.create_table(
            "recurring_journals",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("template_id", sa.Integer, sa.ForeignKey("journal_templates.id"), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("frequency", sa.String(20), nullable=False),
            sa.Column("next_run_date", sa.Date, nullable=False, index=True),
            sa.Column("end_date", sa.Date),
            sa.Column("is_active", sa.Boolean, default=True),
            sa.Column("created_at", sa.DateTime),
        )

    if not _has_table("vendor_bills"):
        op.create_table(
            "vendor_bills",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("number", sa.String(20), nullable=False, index=True),
            sa.Column("vendor_id", sa.Integer, sa.ForeignKey("vendors.id")),
            sa.Column("supplier_invoice_number", sa.String(50)),
            sa.Column("issue_date", sa.Date, nullable=False),
            sa.Column("due_date", sa.Date, nullable=False),
            sa.Column("payment_method", sa.String(20), nullable=False),
            sa.Column("currency", sa.String(3), default="SAR"),
            sa.Column("subtotal", sa.Numeric(15, 4), default=0),
            sa.Column("tax_rate", sa.Numeric(5, 2), default=0),
            sa.Column("tax_amount", sa.Numeric(15, 4), default=0),
            sa.Column("total", sa.Numeric(15, 4), default=0),
            sa.Column("paid_amount", sa.Numeric(15, 4), default=0),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("notes", sa.Text),
            sa.Column("journal_entry_id", sa.Integer, sa.ForeignKey("journal_entries.id")),
            sa.Column("created_at", sa.DateTime),
            sa.UniqueConstraint("company_id", "number", name="uq_vendor_bill_number"),
        )

    if not _has_table("vendor_bill_items"):
        op.create_table(
            "vendor_bill_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("bill_id", sa.Integer, sa.ForeignKey("vendor_bills.id"), nullable=False),
            sa.Column("description", sa.String(255), nullable=False),
            sa.Column("line_type", sa.String(20), nullable=False),
            sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
            sa.Column("quantity", sa.Numeric(10, 2), default=1),
            sa.Column("unit_price", sa.Numeric(15, 4), default=0),
            sa.Column("line_total", sa.Numeric(15, 4), default=0),
            sa.Column("useful_life_years", sa.Integer),
            sa.Column("salvage_value", sa.Numeric(15, 4), default=0),
            sa.Column("created_asset_id", sa.Integer, sa.ForeignKey("fixed_assets.id")),
        )

    if not _has_table("vendor_bill_payments"):
        op.create_table(
            "vendor_bill_payments",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("bill_id", sa.Integer, sa.ForeignKey("vendor_bills.id"), nullable=False),
            sa.Column("amount", sa.Numeric(15, 4), nullable=False),
            sa.Column("payment_date", sa.Date, nullable=False),
            sa.Column("payment_method_id", sa.Integer, sa.ForeignKey("payment_methods.id")),
            sa.Column("method", sa.String(30), default="cash"),
            sa.Column("notes", sa.Text),
            sa.Column("journal_entry_id", sa.Integer, sa.ForeignKey("journal_entries.id")),
            sa.Column("created_at", sa.DateTime),
        )

    if not _has_table("depreciation_entries"):
        op.create_table(
            "depreciation_entries",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("asset_id", sa.Integer, sa.ForeignKey("fixed_assets.id"), nullable=False),
            sa.Column("period_year", sa.Integer, nullable=False),
            sa.Column("period_month", sa.Integer, nullable=False),
            sa.Column("amount", sa.Numeric(15, 4), nullable=False),
            sa.Column("journal_entry_id", sa.Integer, sa.ForeignKey("journal_entries.id")),
            sa.Column("book_value_after", sa.Numeric(15, 4)),
            sa.Column("created_at", sa.DateTime, index=True),
            sa.UniqueConstraint("asset_id", "period_year", "period_month",
                                name="uq_depreciation_asset_period"),
        )

    if not _has_table("agent_messages"):
        op.create_table(
            "agent_messages",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime, index=True),
        )

    # ─── Companies — new VAT default ───────────────────────────────────
    _add_col("companies", "vat_rate", sa.Numeric(5, 2))

    # ─── Invoices — discount, internal notes, reminders ────────────────
    _add_col("invoices", "invoice_discount_type", sa.String(20))
    _add_col("invoices", "invoice_discount_value", sa.Numeric(15, 4))
    _add_col("invoices", "invoice_discount_amount", sa.Numeric(15, 4))
    _add_col("invoices", "taxable_base", sa.Numeric(15, 4))
    _add_col("invoices", "internal_notes", sa.Text)
    _add_col("invoices", "send_reminders", sa.Boolean, server_default=sa.true())
    _add_col("invoices", "reminder_7d_sent_at", sa.DateTime)
    _add_col("invoices", "reminder_3d_sent_at", sa.DateTime)
    _add_col("invoices", "overdue_notified_at", sa.DateTime)

    # ─── Invoice items — product link + discount ───────────────────────
    _add_col("invoice_items", "product_id", sa.Integer)
    _add_col("invoice_items", "discount_type", sa.String(20))
    _add_col("invoice_items", "discount_value", sa.Numeric(15, 4))
    _add_col("invoice_items", "line_total", sa.Numeric(15, 4))

    # ─── Payments — link to payment method ─────────────────────────────
    _add_col("payments", "payment_method_id", sa.Integer)

    # ─── Journal entries — number + pause/reactivate audit ─────────────
    _add_col("journal_entries", "number", sa.String(20))
    _add_col("journal_entries", "is_active", sa.Boolean, server_default=sa.true())
    _add_col("journal_entries", "pause_reason", sa.Text)
    _add_col("journal_entries", "paused_by_id", sa.Integer)
    _add_col("journal_entries", "paused_at", sa.DateTime)
    _add_col("journal_entries", "reactivate_reason", sa.Text)
    _add_col("journal_entries", "reactivated_by_id", sa.Integer)
    _add_col("journal_entries", "reactivated_at", sa.DateTime)

    # ─── Payroll runs — number ─────────────────────────────────────────
    _add_col("payroll_runs", "number", sa.String(20))

    # ─── Payroll lines — variable monthly fields ───────────────────────
    _add_col("payroll_lines", "working_days", sa.Integer, server_default="30")
    _add_col("payroll_lines", "bonus", sa.Numeric(15, 2), server_default="0")
    _add_col("payroll_lines", "absence_deduction", sa.Numeric(15, 2), server_default="0")
    _add_col("payroll_lines", "late_deduction", sa.Numeric(15, 2), server_default="0")
    _add_col("payroll_lines", "advance_deduction", sa.Numeric(15, 2), server_default="0")

    # ─── Employees — extended fields ───────────────────────────────────
    _add_col("employees", "employee_number", sa.String(20))
    _add_col("employees", "phone", sa.String(30))
    _add_col("employees", "start_date", sa.Date)
    _add_col("employees", "contract_type", sa.String(20))
    _add_col("employees", "status", sa.String(20))
    _add_col("employees", "termination_date", sa.Date)
    _add_col("employees", "termination_reason", sa.String(30))
    _add_col("employees", "termination_notes", sa.Text)

    # ─── Fixed assets — vendor link + source bill ──────────────────────
    _add_col("fixed_assets", "vendor_id", sa.Integer)
    _add_col("fixed_assets", "source_bill_id", sa.Integer)

    # ─── Account renaming: استهلاك → إهلاك الأصول الثابتة ─────────────
    op.execute(
        "UPDATE accounts SET name='Fixed Assets Depreciation Expense', "
        "name_ar='مصاريف إهلاك الأصول الثابتة' WHERE code='5250'"
    )
    op.execute(
        "UPDATE accounts SET name='Accumulated Depreciation — Fixed Assets', "
        "name_ar='مجمع إهلاك الأصول الثابتة' WHERE code='1290'"
    )

    # ─── Backfill: existing active employees get default status ────────
    op.execute("UPDATE employees SET status='ACTIVE' WHERE status IS NULL AND is_active=1")
    op.execute("UPDATE employees SET status='TERMINATED' WHERE status IS NULL AND is_active=0")
    op.execute("UPDATE employees SET contract_type='FULL_TIME' WHERE contract_type IS NULL")

    # ─── Backfill: existing journals get is_active=True ────────────────
    op.execute("UPDATE journal_entries SET is_active=1 WHERE is_active IS NULL")

    # ─── Backfill: existing invoices get send_reminders=True ──────────
    op.execute("UPDATE invoices SET send_reminders=1 WHERE send_reminders IS NULL")

    # ─── Backfill: payroll_lines working_days = 30 ─────────────────────
    op.execute("UPDATE payroll_lines SET working_days=30 WHERE working_days IS NULL")
    op.execute("UPDATE payroll_lines SET bonus=0 WHERE bonus IS NULL")
    op.execute("UPDATE payroll_lines SET absence_deduction=0 WHERE absence_deduction IS NULL")
    op.execute("UPDATE payroll_lines SET late_deduction=0 WHERE late_deduction IS NULL")
    op.execute("UPDATE payroll_lines SET advance_deduction=0 WHERE advance_deduction IS NULL")


def downgrade():
    # No-op: this migration only adds columns/tables, never destructively.
    # If you need to reverse, restore the database from a backup.
    pass
