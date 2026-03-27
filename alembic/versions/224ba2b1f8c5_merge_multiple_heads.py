"""merge multiple heads

Revision ID: 224ba2b1f8c5
Revises: 1b9a0914276e, 744b9da5ed66
Create Date: 2026-03-26 20:29:24.599014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '224ba2b1f8c5'
down_revision: Union[str, Sequence[str], None] = ('1b9a0914276e', '744b9da5ed66')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
