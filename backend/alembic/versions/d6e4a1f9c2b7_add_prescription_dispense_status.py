"""add dispense status columns to prescriptions

Revision ID: d6e4a1f9c2b7
Revises: c0ffee5ledger
Create Date: 2026-07-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6e4a1f9c2b7"
down_revision: Union[str, Sequence[str], None] = "c0ffee5ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prescriptions", sa.Column("dispense_status", sa.String(length=20), nullable=True))
    op.add_column("prescriptions", sa.Column("dispensed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prescriptions", sa.Column("dispensed_by", sa.String(), nullable=True))

    op.execute("UPDATE prescriptions SET dispense_status = 'pending' WHERE dispense_status IS NULL")

    op.create_index("ix_prescriptions_dispense_status", "prescriptions", ["dispense_status"], unique=False)
    op.create_index("ix_prescriptions_dispensed_by", "prescriptions", ["dispensed_by"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_prescriptions_dispensed_by", table_name="prescriptions")
    op.drop_index("ix_prescriptions_dispense_status", table_name="prescriptions")
    op.drop_column("prescriptions", "dispensed_by")
    op.drop_column("prescriptions", "dispensed_at")
    op.drop_column("prescriptions", "dispense_status")
