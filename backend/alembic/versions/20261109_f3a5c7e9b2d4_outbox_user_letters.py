"""e-mail outbox: letters to staff — invitation / password reset

Revision ID: f3a5c7e9b2d4
Revises: e2f4b6a8c1d3
Create Date: 2026-11-09 12:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a5c7e9b2d4"
down_revision: Union[str, Sequence[str], None] = "e2f4b6a8c1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_outbox", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_email_outbox_user_id_users", "email_outbox", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_email_outbox_user_id", "email_outbox", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_user_id", table_name="email_outbox")
    op.drop_constraint("fk_email_outbox_user_id_users", "email_outbox", type_="foreignkey")
    op.drop_column("email_outbox", "user_id")
