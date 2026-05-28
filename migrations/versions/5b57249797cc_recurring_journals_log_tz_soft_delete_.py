"""recurring journals log + tz + soft delete (T10)

Revision ID: 5b57249797cc
Revises: 96d3c51d9ba1
Create Date: 2026-05-28 22:49:32.994130

Idempotent. Adds:
  - recurring_journal_logs table (with two indices)
  - companies.timezone (default Asia/Riyadh)
  - recurring_journals.is_deleted (soft-delete flag, default False)
Backfills timezone and is_deleted defaults so existing rows are valid.
"""
from alembic import op
import sqlalchemy as sa


revision = '5b57249797cc'
down_revision = '96d3c51d9ba1'
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


def _has_index(table, idx):
    if not _has_table(table):
        return False
    return idx in {i["name"] for i in _inspector().get_indexes(table)}


def upgrade():
    bind = op.get_bind()

    # ── recurring_journal_logs ──────────────────────────────────────────
    if not _has_table("recurring_journal_logs"):
        op.create_table(
            "recurring_journal_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("recurring_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.Enum("EXECUTE", "FAIL", "EDIT", "STOP", "RESUME", "DELETE",
                                        name="recurringaction"), nullable=False),
            sa.Column("period_posted", sa.Date(), nullable=True),
            sa.Column("journal_entry_id", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
            sa.ForeignKeyConstraint(["recurring_id"], ["recurring_journals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("recurring_journal_logs", "ix_recurring_journal_logs_created_at"):
        with op.batch_alter_table("recurring_journal_logs", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_recurring_journal_logs_created_at"),
                ["created_at"], unique=False,
            )
    if not _has_index("recurring_journal_logs", "ix_recurring_journal_logs_recurring_id"):
        with op.batch_alter_table("recurring_journal_logs", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_recurring_journal_logs_recurring_id"),
                ["recurring_id"], unique=False,
            )

    # ── companies.timezone ──────────────────────────────────────────────
    if not _has_column("companies", "timezone"):
        with op.batch_alter_table("companies", schema=None) as batch_op:
            batch_op.add_column(sa.Column("timezone", sa.String(length=50), nullable=True))
        bind.execute(sa.text(
            "UPDATE companies SET timezone = 'Asia/Riyadh' WHERE timezone IS NULL"
        ))

    # ── recurring_journals.is_deleted ───────────────────────────────────
    if not _has_column("recurring_journals", "is_deleted"):
        with op.batch_alter_table("recurring_journals", schema=None) as batch_op:
            batch_op.add_column(sa.Column("is_deleted", sa.Boolean(), nullable=True))
        bind.execute(sa.text(
            "UPDATE recurring_journals SET is_deleted = 0 WHERE is_deleted IS NULL"
        ))


def downgrade():
    if _has_column("recurring_journals", "is_deleted"):
        with op.batch_alter_table("recurring_journals", schema=None) as batch_op:
            batch_op.drop_column("is_deleted")

    if _has_column("companies", "timezone"):
        with op.batch_alter_table("companies", schema=None) as batch_op:
            batch_op.drop_column("timezone")

    if _has_table("recurring_journal_logs"):
        with op.batch_alter_table("recurring_journal_logs", schema=None) as batch_op:
            if _has_index("recurring_journal_logs", "ix_recurring_journal_logs_recurring_id"):
                batch_op.drop_index(batch_op.f("ix_recurring_journal_logs_recurring_id"))
            if _has_index("recurring_journal_logs", "ix_recurring_journal_logs_created_at"):
                batch_op.drop_index(batch_op.f("ix_recurring_journal_logs_created_at"))
        op.drop_table("recurring_journal_logs")
