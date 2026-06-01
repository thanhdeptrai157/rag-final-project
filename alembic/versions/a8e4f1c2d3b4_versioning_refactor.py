"""versioning refactor

Revision ID: a8e4f1c2d3b4
Revises: c188fa07bcec
Create Date: 2026-05-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a8e4f1c2d3b4"
down_revision: Union[str, Sequence[str], None] = "c188fa07bcec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("previous_version_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("source_file_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("source_mime_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("source_checksum", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.create_foreign_key(
        "fk_document_versions_previous_version_id",
        "document_versions",
        "document_versions",
        ["previous_version_id"],
        ["version_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_versions_previous_version_id",
        "document_versions",
        ["previous_version_id"],
        unique=False,
    )

    op.add_column(
        "processing_jobs",
        sa.Column("version_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_processing_jobs_version_id",
        "processing_jobs",
        "document_versions",
        ["version_id"],
        ["version_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_processing_jobs_version_id",
        "processing_jobs",
        ["version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_version_id", table_name="processing_jobs")
    op.drop_constraint(
        "fk_processing_jobs_version_id",
        "processing_jobs",
        type_="foreignkey",
    )
    op.drop_column("processing_jobs", "version_id")

    op.drop_index(
        "ix_document_versions_previous_version_id",
        table_name="document_versions",
    )
    op.drop_constraint(
        "fk_document_versions_previous_version_id",
        "document_versions",
        type_="foreignkey",
    )
    op.drop_column("document_versions", "status")
    op.drop_column("document_versions", "source_checksum")
    op.drop_column("document_versions", "source_mime_type")
    op.drop_column("document_versions", "source_file_path")
    op.drop_column("document_versions", "previous_version_id")
