"""invitations + company parent_id (T12)

Revision ID: 5717814e0264
Revises: 91cfd2fe95d9
Create Date: 2026-05-28 23:48:04.648697

Idempotent. Adds:
  - companies.parent_id (self-FK, nullable)
  - invitations table + three indices (company_id, email, token-unique)
Backfills:
  - Sets user_companies.role = 'owner' for any rows where role is NULL (legacy).
"""
from alembic import op
import sqlalchemy as sa


revision = '5717814e0264'
down_revision = '91cfd2fe95d9'
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

    # ── invitations ─────────────────────────────────────────────────────
    if not _has_table("invitations"):
        op.create_table(
            "invitations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=150), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("token", sa.String(length=255), nullable=False),
            sa.Column("invited_by_id", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("invitations", "ix_invitations_company_id"):
        with op.batch_alter_table("invitations", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_invitations_company_id"), ["company_id"], unique=False)
    if not _has_index("invitations", "ix_invitations_email"):
        with op.batch_alter_table("invitations", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_invitations_email"), ["email"], unique=False)
    if not _has_index("invitations", "ix_invitations_token"):
        with op.batch_alter_table("invitations", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_invitations_token"), ["token"], unique=True)

    # ── companies.parent_id ─────────────────────────────────────────────
    if not _has_column("companies", "parent_id"):
        with op.batch_alter_table("companies", schema=None) as batch_op:
            batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key("fk_companies_parent_id", "companies", ["parent_id"], ["id"])

    # ── Backfill: ensure every user_companies row has a role ────────────
    if _has_column("user_companies", "role"):
        bind.execute(sa.text(
            "UPDATE user_companies SET role = 'owner' WHERE role IS NULL OR role = ''"
        ))


def downgrade():
    if _has_column("companies", "parent_id"):
        with op.batch_alter_table("companies", schema=None) as batch_op:
            try:
                batch_op.drop_constraint("fk_companies_parent_id", type_="foreignkey")
            except Exception:
                pass
            batch_op.drop_column("parent_id")

    if _has_table("invitations"):
        with op.batch_alter_table("invitations", schema=None) as batch_op:
            if _has_index("invitations", "ix_invitations_token"):
                batch_op.drop_index(batch_op.f("ix_invitations_token"))
            if _has_index("invitations", "ix_invitations_email"):
                batch_op.drop_index(batch_op.f("ix_invitations_email"))
            if _has_index("invitations", "ix_invitations_company_id"):
                batch_op.drop_index(batch_op.f("ix_invitations_company_id"))
        op.drop_table("invitations")
