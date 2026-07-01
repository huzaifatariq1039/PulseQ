"""add pharmacy ledger (expenses, credits, distributors) and prescriptions tables

Adds the new tables introduced by the Expense / Credit / Distributor modules and
the doctor prescription feature. Uses metadata.create_all(checkfirst=True) — the
same pattern as the initial migration — so it creates ONLY the missing tables and
never alters or drops existing ones (safe for production data).

New tables created:
    - pharmacy_expenses
    - pharmacy_credits
    - pharmacy_credit_payments
    - pharmacy_distributors
    - prescriptions

Revision ID: c0ffee5ledger
Revises: b58948a9759b
Create Date: 2026-06-29
"""
from typing import Sequence, Union

from alembic import op
from app.database import Base
import app.db_models  # noqa: F401  Import models so they register on Base.metadata

# revision identifiers, used by Alembic.
revision: str = "c0ffee5ledger"
down_revision: Union[str, Sequence[str], None] = "b58948a9759b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the new tables. checkfirst=True => only missing tables are created."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Drop only the tables introduced by this revision."""
    for table in (
        "prescriptions",
        "pharmacy_credit_payments",
        "pharmacy_credits",
        "pharmacy_distributors",
        "pharmacy_expenses",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
