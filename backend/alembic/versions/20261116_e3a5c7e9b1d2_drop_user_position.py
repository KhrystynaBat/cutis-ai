"""drop users.position: the role already says who the staff member is

Revision ID: e3a5c7e9b1d2
Revises: d2f4a6c8e0b1
Create Date: 2026-11-16 12:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a5c7e9b1d2"
down_revision: Union[str, Sequence[str], None] = "d2f4a6c8e0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "position")


def downgrade() -> None:
    op.add_column("users", sa.Column("position", sa.String(length=100), nullable=True))
