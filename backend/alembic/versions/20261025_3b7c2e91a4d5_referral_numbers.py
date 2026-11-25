"""referral numbers and case decision constraints

Revision ID: 3b7c2e91a4d5
Revises: 6850edb1a1d2
Create Date: 2026-10-25 20:10:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '3b7c2e91a4d5'
down_revision: Union[str, Sequence[str], None] = '6850edb1a1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SEQUENCE referral_number_seq START 1")
    # a planned follow-up always has a date
    op.create_check_constraint(
        "follow_up_has_date",
        "cases",
        "status <> 'FollowUpPlanned' OR follow_up_date IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("follow_up_has_date", "cases", type_="check")
    op.execute("DROP SEQUENCE referral_number_seq")
