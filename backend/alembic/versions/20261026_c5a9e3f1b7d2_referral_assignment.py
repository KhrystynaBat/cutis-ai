"""referral assignment to a lab specialist

Revision ID: c5a9e3f1b7d2
Revises: 8d4f1a6c2e70
Create Date: 2026-10-26 10:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c5a9e3f1b7d2'
down_revision: Union[str, Sequence[str], None] = '8d4f1a6c2e70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("referrals", sa.Column("assigned_lab_specialist_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("referrals", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_referrals_assigned_lab_specialist_id_users",
        "referrals",
        "users",
        ["assigned_lab_specialist_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_referrals_assigned_lab_specialist_id", "referrals", ["assigned_lab_specialist_id"])

    op.execute(
        """
        UPDATE referrals r
           SET assigned_lab_specialist_id = lr.lab_specialist_id,
               assigned_at = COALESCE(r.started_at, r.completed_at, lr.updated_at)
          FROM lab_results lr
         WHERE lr.referral_id = r.id AND r.status IN ('InProgress', 'Completed')
        """
    )
    op.execute(
        "UPDATE referrals SET status = 'Sent', started_at = NULL "
        "WHERE status = 'InProgress' AND assigned_lab_specialist_id IS NULL"
    )

    op.create_check_constraint(
        "assignment_matches_status",
        "referrals",
        "(status = 'Sent') = (assigned_lab_specialist_id IS NULL)",
    )
    op.create_check_constraint(
        "assignment_has_time",
        "referrals",
        "(assigned_lab_specialist_id IS NULL) = (assigned_at IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("assignment_has_time", "referrals", type_="check")
    op.drop_constraint("assignment_matches_status", "referrals", type_="check")
    op.drop_index("ix_referrals_assigned_lab_specialist_id", table_name="referrals")
    op.drop_constraint("fk_referrals_assigned_lab_specialist_id_users", "referrals", type_="foreignkey")
    op.drop_column("referrals", "assigned_at")
    op.drop_column("referrals", "assigned_lab_specialist_id")
