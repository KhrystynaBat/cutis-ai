"""dermoscopy filter result on case photos

Revision ID: c9e1a3b5d7f9
Revises: b8d0f2a4c6e8
Create Date: 2026-11-15 01:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9e1a3b5d7f9"
down_revision: Union[str, Sequence[str], None] = "b8d0f2a4c6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("case_images", sa.Column("gate_score", sa.Float(), nullable=True))
    op.add_column("case_images", sa.Column("gate_passed", sa.Boolean(), nullable=True))
    op.add_column("case_images", sa.Column("gate_model_sha256", sa.String(length=64), nullable=True))
    op.add_column("case_images", sa.Column("gate_confirmed_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("case_images", sa.Column("gate_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_case_images_gate_confirmed_by_id_users"),
        "case_images",
        "users",
        ["gate_confirmed_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_case_images_gate_confirmed_by_id_users"), "case_images", type_="foreignkey")
    op.drop_column("case_images", "gate_confirmed_at")
    op.drop_column("case_images", "gate_confirmed_by_id")
    op.drop_column("case_images", "gate_model_sha256")
    op.drop_column("case_images", "gate_passed")
    op.drop_column("case_images", "gate_score")
