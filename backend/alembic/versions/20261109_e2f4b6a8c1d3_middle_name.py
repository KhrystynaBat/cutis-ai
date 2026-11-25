"""middle name (по батькові) for users and patients

Revision ID: e2f4b6a8c1d3
Revises: c5a9e3f1b7d2
Create Date: 2026-11-09 10:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f4b6a8c1d3"
down_revision: Union[str, Sequence[str], None] = "c5a9e3f1b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("middle_name", sa.String(length=100), nullable=True))
    op.add_column("patients", sa.Column("middle_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("patients", "middle_name")
    op.drop_column("users", "middle_name")
