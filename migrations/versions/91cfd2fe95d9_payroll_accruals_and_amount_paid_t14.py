"""payroll accruals and amount_paid (T14)

Revision ID: 91cfd2fe95d9
Revises: 5b57249797cc
Create Date: 2026-05-28 23:04:32.303672

Idempotent. Adds:
  - payroll_lines.amount_paid (defaults backfilled to net for existing rows)
  - employee_accruals table (with two indices)
"""
from alembic import op
import sqlalchemy as sa


revision = '91cfd2fe95d9'
down_revision = '5b57249797cc'
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

    # ── payroll_lines.amount_paid ───────────────────────────────────────
    if not _has_column("payroll_lines", "amount_paid"):
        with op.batch_alter_table("payroll_lines", schema=None) as batch_op:
            batch_op.add_column(sa.Column("amount_paid", sa.Numeric(precision=15, scale=2), nullable=True))
        # Backfill: assume existing rows were fully paid (amount_paid = net)
        bind.execute(sa.text(
            "UPDATE payroll_lines SET amount_paid = net WHERE amount_paid IS NULL"
        ))

    # ── employee_accruals ───────────────────────────────────────────────
    if not _has_table("employee_accruals"):
        op.create_table(
            "employee_accruals",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("source_run_id", sa.Integer(), nullable=True),
            sa.Column("source_line_id", sa.Integer(), nullable=True),
            sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column("settled_at", sa.DateTime(), nullable=True),
            sa.Column("settlement_journal_entry_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
            sa.ForeignKeyConstraint(["settlement_journal_entry_id"], ["journal_entries.id"]),
            sa.ForeignKeyConstraint(["source_line_id"], ["payroll_lines.id"]),
            sa.ForeignKeyConstraint(["source_run_id"], ["payroll_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("employee_accruals", "ix_employee_accruals_company_id"):
        with op.batch_alter_table("employee_accruals", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_employee_accruals_company_id"),
                ["company_id"], unique=False,
            )
    if not _has_index("employee_accruals", "ix_employee_accruals_employee_id"):
        with op.batch_alter_table("employee_accruals", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_employee_accruals_employee_id"),
                ["employee_id"], unique=False,
            )


def downgrade():
    if _has_column("payroll_lines", "amount_paid"):
        with op.batch_alter_table("payroll_lines", schema=None) as batch_op:
            batch_op.drop_column("amount_paid")

    if _has_table("employee_accruals"):
        with op.batch_alter_table("employee_accruals", schema=None) as batch_op:
            if _has_index("employee_accruals", "ix_employee_accruals_employee_id"):
                batch_op.drop_index(batch_op.f("ix_employee_accruals_employee_id"))
            if _has_index("employee_accruals", "ix_employee_accruals_company_id"):
                batch_op.drop_index(batch_op.f("ix_employee_accruals_company_id"))
        op.drop_table("employee_accruals")
