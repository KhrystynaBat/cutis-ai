"""lab results: approval and completion constraints, unread notifications index

Revision ID: 8d4f1a6c2e70
Revises: 3b7c2e91a4d5
Create Date: 2026-10-25 23:40:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8d4f1a6c2e70'
down_revision: Union[str, Sequence[str], None] = '3b7c2e91a4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "approved_is_complete",
        "lab_results",
        "NOT is_approved OR (lab_accession_number IS NOT NULL AND histopathology_diagnosis IS NOT NULL"
        " AND histopathology_description IS NOT NULL AND examined_at IS NOT NULL AND approved_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "completed_has_date",
        "referrals",
        "status <> 'Completed' OR completed_at IS NOT NULL",
    )
    # the bell polls the unread count
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("NOT is_read"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_constraint("completed_has_date", "referrals", type_="check")
    op.drop_constraint("approved_is_complete", "lab_results", type_="check")
