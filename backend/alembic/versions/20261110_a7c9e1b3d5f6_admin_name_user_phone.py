"""optional administrator name, user phone

Revision ID: a7c9e1b3d5f6
Revises: f3a5c7e9b2d4
Create Date: 2026-11-10 10:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c9e1b3d5f6"
down_revision: Union[str, Sequence[str], None] = "f3a5c7e9b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "first_name", existing_type=sa.String(length=100), nullable=True)
    op.alter_column("users", "last_name", existing_type=sa.String(length=100), nullable=True)
    op.create_check_constraint(
        "staff_has_name", "users", "role = 'Admin' OR (first_name IS NOT NULL AND last_name IS NOT NULL)"
    )
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_constraint("staff_has_name", "users", type_="check")
    op.execute("UPDATE users SET first_name = 'Адміністратор' WHERE first_name IS NULL")
    op.execute("UPDATE users SET last_name = 'Системи' WHERE last_name IS NULL")
    op.alter_column("users", "last_name", existing_type=sa.String(length=100), nullable=False)
    op.alter_column("users", "first_name", existing_type=sa.String(length=100), nullable=False)
