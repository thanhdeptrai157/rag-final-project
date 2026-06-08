"""add chat sessions feedback traces

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("anonymous_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_sessions_anonymous_id"),
        "chat_sessions",
        ["anonymous_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_sessions_deleted_at"),
        "chat_sessions",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_sessions_updated_at"),
        "chat_sessions",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_sessions_user_id"),
        "chat_sessions",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_chat_messages_role",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_messages_created_at"),
        "chat_messages",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_messages_session_id"),
        "chat_messages",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "message_rag_traces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("route", sa.String(length=50), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column(
            "retrieved_contexts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"], ["chat_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index(
        op.f("ix_message_rag_traces_latency_ms"),
        "message_rag_traces",
        ["latency_ms"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_rag_traces_message_id"),
        "message_rag_traces",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_rag_traces_route"),
        "message_rag_traces",
        ["route"],
        unique=False,
    )

    op.create_table(
        "message_feedbacks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column(
            "admin_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_message_feedbacks_rating",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN "
            "('incorrect', 'incomplete', 'irrelevant', 'bad_citation', 'outdated', 'other')",
            name="ck_message_feedbacks_reason",
        ),
        sa.CheckConstraint(
            "admin_status IN ('open', 'reviewed', 'resolved')",
            name="ck_message_feedbacks_admin_status",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.user_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_message_feedbacks_admin_status"),
        "message_feedbacks",
        ["admin_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_feedbacks_created_at"),
        "message_feedbacks",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_feedbacks_message_id"),
        "message_feedbacks",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_feedbacks_rating"),
        "message_feedbacks",
        ["rating"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_feedbacks_reason"),
        "message_feedbacks",
        ["reason"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_feedbacks_user_id"),
        "message_feedbacks",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_message_feedbacks_message_user",
        "message_feedbacks",
        ["message_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_message_feedbacks_message_user", table_name="message_feedbacks"
    )
    op.drop_index(
        op.f("ix_message_feedbacks_user_id"), table_name="message_feedbacks"
    )
    op.drop_index(
        op.f("ix_message_feedbacks_reason"), table_name="message_feedbacks"
    )
    op.drop_index(
        op.f("ix_message_feedbacks_rating"), table_name="message_feedbacks"
    )
    op.drop_index(
        op.f("ix_message_feedbacks_message_id"), table_name="message_feedbacks"
    )
    op.drop_index(
        op.f("ix_message_feedbacks_created_at"), table_name="message_feedbacks"
    )
    op.drop_index(
        op.f("ix_message_feedbacks_admin_status"), table_name="message_feedbacks"
    )
    op.drop_table("message_feedbacks")

    op.drop_index(
        op.f("ix_message_rag_traces_route"), table_name="message_rag_traces"
    )
    op.drop_index(
        op.f("ix_message_rag_traces_message_id"),
        table_name="message_rag_traces",
    )
    op.drop_index(
        op.f("ix_message_rag_traces_latency_ms"),
        table_name="message_rag_traces",
    )
    op.drop_table("message_rag_traces")

    op.drop_index(op.f("ix_chat_messages_session_id"), table_name="chat_messages")
    op.drop_index(op.f("ix_chat_messages_created_at"), table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index(op.f("ix_chat_sessions_user_id"), table_name="chat_sessions")
    op.drop_index(op.f("ix_chat_sessions_updated_at"), table_name="chat_sessions")
    op.drop_index(op.f("ix_chat_sessions_deleted_at"), table_name="chat_sessions")
    op.drop_index(op.f("ix_chat_sessions_anonymous_id"), table_name="chat_sessions")
    op.drop_table("chat_sessions")
