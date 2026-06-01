"""drop document file columns

Revision ID: b1c2d3e4f5a6
Revises: a8e4f1c2d3b4
Create Date: 2026-05-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a8e4f1c2d3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("documents", "file_path")
    op.drop_column("documents", "source_path")


def downgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("source_path", sa.Text(), nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("file_path", sa.Text(), nullable=True),
    )
