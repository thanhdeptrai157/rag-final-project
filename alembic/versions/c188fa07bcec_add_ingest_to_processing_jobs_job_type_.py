"""add ingest to processing_jobs job_type constraint

Revision ID: c188fa07bcec
Revises: 0baa7a1aa676
Create Date: 2026-04-16 22:21:39.381233

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c188fa07bcec"
down_revision: Union[str, Sequence[str], None] = "0baa7a1aa676"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.drop_constraint(
        "ck_processing_jobs_job_type",
        "processing_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_processing_jobs_job_type",
        "processing_jobs",
        "job_type IN ('upload', 'ocr', 'extract', 'chunk', 'embed', 'index', 'ingest')",
    )


def downgrade():
    op.drop_constraint(
        "ck_processing_jobs_job_type",
        "processing_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_processing_jobs_job_type",
        "processing_jobs",
        "job_type IN ('upload', 'ocr', 'extract', 'chunk', 'embed', 'index')",
    )
