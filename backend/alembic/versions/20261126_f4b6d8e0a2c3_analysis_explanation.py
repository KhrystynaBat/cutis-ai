"""ai_analyses: text explanation from Gemini

Revision ID: f4b6d8e0a2c3
Revises: e3a5c7e9b1d2
Create Date: 2026-11-26 12:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f4b6d8e0a2c3"
down_revision: Union[str, Sequence[str], None] = "e3a5c7e9b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_analyses",
        sa.Column(
            "explanation_status",
            sa.Enum(
                "Pending",
                "Completed",
                "Failed",
                name="explanation_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
    )
    op.add_column("ai_analyses", sa.Column("explanation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("ai_analyses", sa.Column("explanation_model", sa.String(length=64), nullable=True))
    op.add_column("ai_analyses", sa.Column("explanation_error_code", sa.String(length=64), nullable=True))
    op.add_column("ai_analyses", sa.Column("explanation_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_analyses", "explanation_updated_at")
    op.drop_column("ai_analyses", "explanation_error_code")
    op.drop_column("ai_analyses", "explanation_model")
    op.drop_column("ai_analyses", "explanation_json")
    op.drop_column("ai_analyses", "explanation_status")
