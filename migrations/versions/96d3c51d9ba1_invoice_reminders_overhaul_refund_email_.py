"""invoice reminders overhaul + refund email (T13)

Revision ID: 96d3c51d9ba1
Revises: 5fa2b4c2f255
Create Date: 2026-05-28 22:41:49.106738

Idempotent: safe to re-run against a partially-migrated DB. Each operation
checks current schema state via sa.inspect() before applying.

Adds:
  - companies.reminder_config (JSON-as-text)
  - invoice_reminders_sent table (replaces individual reminder_*_sent_at columns)

Backfills:
  - Copies any non-null reminder_7d_sent_at / reminder_3d_sent_at /
    overdue_notified_at values from invoices into invoice_reminders_sent rows.
  - Seeds default PaymentMethods (Cash → 1110, Bank Transfer → 1120) for any
    company that has zero payment methods.

Then drops the legacy reminder_*_sent_at columns.
"""
from alembic import op
import sqlalchemy as sa


revision = '96d3c51d9ba1'
down_revision = '5fa2b4c2f255'
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name):
    return name in _inspector().get_table_names()


def _has_column(table, col):
    if not _has_table(table):
        return False
    return col in {c["name"] for c in _inspector().get_columns(table)}


def upgrade():
    bind = op.get_bind()

    # ── 1. Create invoice_reminders_sent table ──────────────────────────
    if not _has_table("invoice_reminders_sent"):
        op.create_table(
            "invoice_reminders_sent",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("invoice_id", sa.Integer(), nullable=False),
            sa.Column("threshold_kind", sa.String(length=10), nullable=False),
            sa.Column("threshold_days", sa.Integer(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("invoice_id", "threshold_kind", "threshold_days",
                                name="uq_invoice_reminder_threshold"),
        )
        with op.batch_alter_table("invoice_reminders_sent", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_invoice_reminders_sent_invoice_id"),
                ["invoice_id"], unique=False,
            )

    # ── 2. companies.reminder_config ────────────────────────────────────
    if not _has_column("companies", "reminder_config"):
        with op.batch_alter_table("companies", schema=None) as batch_op:
            batch_op.add_column(sa.Column("reminder_config", sa.Text(), nullable=True))

    # ── 3. Backfill from legacy invoice reminder columns ────────────────
    legacy_cols = {
        "reminder_7d_sent_at": ("before", 7),
        "reminder_3d_sent_at": ("before", 3),
        "overdue_notified_at": ("overdue", 0),
    }
    present_legacy = [col for col in legacy_cols if _has_column("invoices", col)]
    for col in present_legacy:
        kind, days = legacy_cols[col]
        rows = bind.execute(
            sa.text(f"SELECT id, {col} FROM invoices WHERE {col} IS NOT NULL")
        ).fetchall()
        for inv_id, sent_at in rows:
            # Skip if a row already exists (rerun safety)
            existing = bind.execute(
                sa.text(
                    "SELECT 1 FROM invoice_reminders_sent "
                    "WHERE invoice_id=:i AND threshold_kind=:k AND threshold_days=:d"
                ),
                {"i": inv_id, "k": kind, "d": days},
            ).first()
            if existing:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO invoice_reminders_sent "
                    "(invoice_id, threshold_kind, threshold_days, sent_at) "
                    "VALUES (:i, :k, :d, :s)"
                ),
                {"i": inv_id, "k": kind, "d": days, "s": sent_at},
            )

    # ── 4. Backfill default payment methods for companies missing them ──
    if _has_table("companies") and _has_table("payment_methods") and _has_table("accounts"):
        companies = bind.execute(sa.text("SELECT id FROM companies")).fetchall()
        for (cid,) in companies:
            count = bind.execute(
                sa.text("SELECT COUNT(*) FROM payment_methods WHERE company_id=:c"),
                {"c": cid},
            ).scalar()
            if count and count > 0:
                continue
            cash_acc = bind.execute(
                sa.text("SELECT id FROM accounts WHERE company_id=:c AND code='1110'"),
                {"c": cid},
            ).scalar()
            bank_acc = bind.execute(
                sa.text("SELECT id FROM accounts WHERE company_id=:c AND code='1120'"),
                {"c": cid},
            ).scalar()
            if cash_acc:
                bind.execute(
                    sa.text(
                        "INSERT INTO payment_methods "
                        "(company_id, name, name_ar, account_id, is_active, is_default) "
                        "VALUES (:c, 'Cash', 'نقدي', :a, 1, 1)"
                    ),
                    {"c": cid, "a": cash_acc},
                )
            if bank_acc:
                bind.execute(
                    sa.text(
                        "INSERT INTO payment_methods "
                        "(company_id, name, name_ar, account_id, is_active, is_default) "
                        "VALUES (:c, 'Bank Transfer', 'حوالة بنكية', :a, 1, 0)"
                    ),
                    {"c": cid, "a": bank_acc},
                )

    # ── 5. Drop legacy reminder columns from invoices ───────────────────
    legacy_present = [c for c in legacy_cols if _has_column("invoices", c)]
    if legacy_present:
        with op.batch_alter_table("invoices", schema=None) as batch_op:
            for col in legacy_present:
                batch_op.drop_column(col)


def downgrade():
    if not _has_column("invoices", "reminder_7d_sent_at"):
        with op.batch_alter_table("invoices", schema=None) as batch_op:
            batch_op.add_column(sa.Column("overdue_notified_at", sa.DATETIME(), nullable=True))
            batch_op.add_column(sa.Column("reminder_3d_sent_at", sa.DATETIME(), nullable=True))
            batch_op.add_column(sa.Column("reminder_7d_sent_at", sa.DATETIME(), nullable=True))

    if _has_column("companies", "reminder_config"):
        with op.batch_alter_table("companies", schema=None) as batch_op:
            batch_op.drop_column("reminder_config")

    if _has_table("invoice_reminders_sent"):
        with op.batch_alter_table("invoice_reminders_sent", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_invoice_reminders_sent_invoice_id"))
        op.drop_table("invoice_reminders_sent")
