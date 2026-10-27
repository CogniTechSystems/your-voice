"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-27 01:57:37.378501
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "language_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repo_id", sa.String(length=200), nullable=False),
        sa.Column("revision", sa.String(length=100), nullable=False),
        sa.Column("allow_patterns", sa.JSON(), nullable=True),
        sa.Column("local_path", sa.String(length=1000), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "downloading",
                "ready",
                "failed",
                name="downloadstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_id"),
    )
    op.create_table(
        "runtimes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("managed", "external", name="runtimekind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("command_template", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("health_path", sa.String(length=200), nullable=False),
        sa.Column("startup_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "writing_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "format",
            sa.Enum(
                "markdown", "html", "text", name="documentformat", native_enum=False, length=20
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("runtime_id", sa.Integer(), nullable=False),
        sa.Column("model_file", sa.String(length=500), nullable=True),
        sa.Column("served_model_name", sa.String(length=200), nullable=True),
        sa.Column("launch_args", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Double(), nullable=False),
        sa.Column("top_p", sa.Double(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("request_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "stopped",
                "starting",
                "running",
                "failed",
                name="deploymentstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["language_models.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["runtime_id"], ["runtimes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("deployment_id", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "deployment_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deployment_id", sa.Integer(), nullable=False),
        sa.Column("line", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("deployment_logs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_deployment_logs_deployment_id"), ["deployment_id"], unique=False
        )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("requested_outputs", sa.JSON(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "completed",
                "cancelled",
                name="jobstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("samples_read", sa.JSON(), nullable=False),
        sa.Column("settings_snapshot", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("working_seconds", sa.Double(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("agent_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_jobs_agent_id"), ["agent_id"], unique=False)

    op.create_table(
        "context_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "format",
            sa.Enum(
                "markdown", "html", "text", name="documentformat", native_enum=False, length=20
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("context_documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_context_documents_job_id"), ["job_id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=200), nullable=False),
        sa.Column(
            "format",
            sa.Enum(
                "markdown", "html", "text", name="documentformat", native_enum=False, length=20
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "path"),
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_documents_job_id"), ["job_id"], unique=False)

    op.create_table(
        "job_samples",
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("sample_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sample_id"], ["writing_samples.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "sample_id"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("main", "highlight", name="conversationkind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "idle", "running", "error", name="conversationstatus", native_enum=False, length=20
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("prefix", sa.Text(), nullable=True),
        sa.Column("suffix", sa.Text(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_conversations_document_id"), ["document_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_conversations_job_id"), ["job_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "tool", name="messagerole", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("tool_call_id", sa.String(length=200), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("agent_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_messages_conversation_id"), ["conversation_id"], unique=False
        )

    op.create_table(
        "document_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "agent",
                "proposal",
                "user",
                "restore",
                name="revisionsource",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "number"),
    )
    with op.batch_alter_table("document_revisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_document_revisions_document_id"), ["document_id"], unique=False
        )

    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("replacement", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "applied",
                "rejected",
                "superseded",
                name="proposalstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_proposals_conversation_id"), ["conversation_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposals_conversation_id"))

    op.drop_table("proposals")
    with op.batch_alter_table("document_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_document_revisions_document_id"))

    op.drop_table("document_revisions")
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_messages_conversation_id"))

    op.drop_table("chat_messages")
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_conversations_job_id"))
        batch_op.drop_index(batch_op.f("ix_conversations_document_id"))

    op.drop_table("conversations")
    op.drop_table("job_samples")
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_job_id"))

    op.drop_table("documents")
    with op.batch_alter_table("context_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_context_documents_job_id"))

    op.drop_table("context_documents")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_jobs_agent_id"))

    op.drop_table("jobs")
    with op.batch_alter_table("deployment_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_deployment_logs_deployment_id"))

    op.drop_table("deployment_logs")
    op.drop_table("agents")
    op.drop_table("deployments")
    op.drop_table("writing_samples")
    op.drop_table("runtimes")
    op.drop_table("language_models")
