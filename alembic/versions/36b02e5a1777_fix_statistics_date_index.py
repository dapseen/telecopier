"""fix_statistics_date_index

Revision ID: 36b02e5a1777
Revises: 5f29694862ad
Create Date: 2024-03-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36b02e5a1777'
down_revision: Union[str, None] = '5f29694862ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop old index and create new one with correct column name."""
    # Drop old index if it exists
    op.execute("DROP INDEX IF EXISTS idx_statistics_date")
    
    # Create new index with correct column name
    op.execute("CREATE INDEX IF NOT EXISTS idx_statistics_date ON daily_statistics (trading_date)")


def downgrade() -> None:
    """Revert index changes."""
    # Drop new index
    op.execute("DROP INDEX IF EXISTS idx_statistics_date")
    
    # Recreate old index
    op.execute("CREATE INDEX IF NOT EXISTS idx_statistics_date ON daily_statistics (date)")
