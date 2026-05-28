"""add cashflow_category to journal_entries (T11)

Revision ID: 5fa2b4c2f255
Revises: 6e0cd4a49d23
Create Date: 2026-05-28 22:35:48.182971

"""
from alembic import op
import sqlalchemy as sa


revision = '5fa2b4c2f255'
down_revision = '6e0cd4a49d23'
branch_labels = None
depends_on = None


def _has_column(table, col):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    if not _has_column("journal_entries", "cashflow_category"):
        with op.batch_alter_table("journal_entries", schema=None) as batch_op:
            batch_op.add_column(sa.Column("cashflow_category", sa.String(length=15), nullable=True))


def downgrade():
    if _has_column("journal_entries", "cashflow_category"):
        with op.batch_alter_table("journal_entries", schema=None) as batch_op:
            batch_op.drop_column("cashflow_category")
