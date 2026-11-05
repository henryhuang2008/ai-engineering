"""Create the initial application schema.

Revision ID: 202611050001
Revises:
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202611050001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "source_documents",
        sa.Column(
            "ticker",
            sa.String(length=10),
            nullable=False,
        ),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("filing_type", sa.String(length=20), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_documents")),
        sa.UniqueConstraint(
            "ticker",
            "accession_number",
            name="ticker_accession",
        ),
    )
    op.create_table(
        "chat_threads",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "title",
            sa.String(length=255),
            server_default="New chat",
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_threads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_threads")),
    )
    op.create_index(
        op.f("ix_chat_threads_user_id"),
        "chat_threads",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "document_chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("source_start", sa.Integer(), nullable=True),
        sa.Column("source_end", sa.Integer(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_documents.id"],
            name=op.f("fk_document_chunks_document_id_source_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="document_chunk_index",
        ),
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"),
        "document_chunks",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_document_chunks_search_vector_gin",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "chat_messages",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name=op.f("ck_chat_messages_valid_role"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            name=op.f("fk_chat_messages_thread_id_chat_threads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    op.create_index(
        op.f("ix_chat_messages_thread_id"),
        "chat_messages",
        ["thread_id"],
        unique=False,
    )
    op.create_table(
        "message_citations",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_message_citations_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name=op.f("fk_message_citations_message_id_chat_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_citations")),
        sa.UniqueConstraint(
            "message_id",
            "citation_index",
            name="message_citation_index",
        ),
    )
    op.create_index(
        op.f("ix_message_citations_chunk_id"),
        "message_citations",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_citations_message_id"),
        "message_citations",
        ["message_id"],
        unique=False,
    )

    op.execute("ALTER TABLE public.users ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY users_select_own ON public.users
        FOR SELECT TO authenticated
        USING (id = (SELECT auth.uid()))
        """
    )
    op.execute(
        """
        CREATE POLICY users_insert_own ON public.users
        FOR INSERT TO authenticated
        WITH CHECK (id = (SELECT auth.uid()))
        """
    )
    op.execute(
        """
        CREATE POLICY users_update_own ON public.users
        FOR UPDATE TO authenticated
        USING (id = (SELECT auth.uid()))
        WITH CHECK (id = (SELECT auth.uid()))
        """
    )

    op.execute("ALTER TABLE public.source_documents ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY source_documents_read_authenticated ON public.source_documents
        FOR SELECT TO authenticated
        USING (true)
        """
    )
    op.execute("ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY document_chunks_read_authenticated ON public.document_chunks
        FOR SELECT TO authenticated
        USING (true)
        """
    )

    op.execute("ALTER TABLE public.chat_threads ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY chat_threads_own ON public.chat_threads
        FOR ALL TO authenticated
        USING (user_id = (SELECT auth.uid()))
        WITH CHECK (user_id = (SELECT auth.uid()))
        """
    )
    op.execute("ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY chat_messages_own ON public.chat_messages
        FOR ALL TO authenticated
        USING (
            EXISTS (
                SELECT 1 FROM public.chat_threads
                WHERE chat_threads.id = chat_messages.thread_id
                  AND chat_threads.user_id = (SELECT auth.uid())
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM public.chat_threads
                WHERE chat_threads.id = chat_messages.thread_id
                  AND chat_threads.user_id = (SELECT auth.uid())
            )
        )
        """
    )
    op.execute("ALTER TABLE public.message_citations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY message_citations_own ON public.message_citations
        FOR ALL TO authenticated
        USING (
            EXISTS (
                SELECT 1
                FROM public.chat_messages
                JOIN public.chat_threads ON chat_threads.id = chat_messages.thread_id
                WHERE chat_messages.id = message_citations.message_id
                  AND chat_threads.user_id = (SELECT auth.uid())
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM public.chat_messages
                JOIN public.chat_threads ON chat_threads.id = chat_messages.thread_id
                WHERE chat_messages.id = message_citations.message_id
                  AND chat_threads.user_id = (SELECT auth.uid())
            )
        )
        """
    )

    op.execute("GRANT SELECT, INSERT, UPDATE ON public.users TO authenticated")
    op.execute("GRANT SELECT, INSERT, UPDATE ON public.chat_threads TO authenticated")
    op.execute("GRANT SELECT, INSERT ON public.chat_messages TO authenticated")
    op.execute("GRANT SELECT ON public.source_documents, public.document_chunks TO authenticated")
    op.execute("GRANT SELECT, INSERT ON public.message_citations TO authenticated")
    op.execute(
        """
        CREATE FUNCTION public.update_chat_thread_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            UPDATE public.chat_threads
            SET updated_at = now()
            WHERE id = NEW.thread_id;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER chat_messages_update_thread_timestamp
        AFTER INSERT ON public.chat_messages
        FOR EACH ROW
        EXECUTE FUNCTION public.update_chat_thread_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER chat_messages_update_thread_timestamp ON public.chat_messages")
    op.execute("DROP FUNCTION public.update_chat_thread_updated_at()")
    op.drop_table("message_citations")
    op.drop_index("ix_chat_messages_thread_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_document_chunks_search_vector_gin", table_name="document_chunks")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index(op.f("ix_chat_threads_user_id"), table_name="chat_threads")
    op.drop_table("chat_threads")
    op.drop_table("source_documents")
    op.drop_table("users")
