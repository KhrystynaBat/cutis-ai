"""staff profile: position, birth date, sex; e-mail change requests

Revision ID: d2f4a6c8e0b1
Revises: c9e1a3b5d7f9
Create Date: 2026-11-16 00:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2f4a6c8e0b1"
down_revision: Union[str, Sequence[str], None] = "c9e1a3b5d7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("position", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("sex", sa.String(length=32), nullable=True))
    op.create_check_constraint(op.f("ck_users_sex"), "users", "sex IN ('Female', 'Male')")

    op.create_table(
        "email_change_requests",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("new_email", sa.String(length=254), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_email_change_requests_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_change_requests")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_change_requests_token_hash")),
    )
    op.create_index(op.f("ix_email_change_requests_user_id"), "email_change_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_change_requests_user_id"), table_name="email_change_requests")
    op.drop_table("email_change_requests")
    op.drop_constraint(op.f("ck_users_sex"), "users", type_="check")
    op.drop_column("users", "sex")
    op.drop_column("users", "birth_date")
    op.drop_column("users", "position")
