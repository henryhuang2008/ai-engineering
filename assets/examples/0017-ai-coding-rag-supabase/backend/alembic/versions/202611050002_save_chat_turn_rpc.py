"""Persist a complete chat turn and its citations atomically.

Revision ID: 202611050002
Revises: 202611050001
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202611050002"
down_revision: str | None = "202611050001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.save_chat_turn(
            p_thread_id uuid,
            p_user_content text,
            p_assistant_content text,
            p_citations jsonb
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
            v_assistant_message_id uuid;
            v_created_at timestamptz := clock_timestamp();
            v_citation jsonb;
            v_citation_index integer := 0;
        BEGIN
            IF auth.uid() IS NULL OR NOT EXISTS (
                SELECT 1
                FROM public.chat_threads
                WHERE id = p_thread_id
                  AND user_id = auth.uid()
            ) THEN
                RAISE EXCEPTION 'Chat thread not found'
                    USING ERRCODE = 'P0002';
            END IF;

            IF p_citations IS NULL
               OR jsonb_typeof(p_citations) <> 'array'
               OR jsonb_array_length(p_citations) > 20 THEN
                RAISE EXCEPTION 'Invalid citation list'
                    USING ERRCODE = '22023';
            END IF;

            INSERT INTO public.chat_messages (thread_id, role, content, created_at)
            VALUES (p_thread_id, 'user', p_user_content, v_created_at);

            INSERT INTO public.chat_messages (thread_id, role, content, created_at)
            VALUES (
                p_thread_id,
                'assistant',
                p_assistant_content,
                v_created_at + interval '1 microsecond'
            )
            RETURNING id INTO v_assistant_message_id;

            FOR v_citation IN SELECT value FROM jsonb_array_elements(p_citations)
            LOOP
                INSERT INTO public.message_citations (
                    message_id,
                    chunk_id,
                    citation_index,
                    quote
                )
                VALUES (
                    v_assistant_message_id,
                    (v_citation->>'chunk_id')::uuid,
                    v_citation_index,
                    v_citation->>'quote'
                );
                v_citation_index := v_citation_index + 1;
            END LOOP;

            RETURN v_assistant_message_id;
        END;
        $$;
        REVOKE ALL ON FUNCTION public.save_chat_turn(uuid, text, text, jsonb) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.save_chat_turn(uuid, text, text, jsonb) TO authenticated;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION public.save_chat_turn(uuid, text, text, jsonb)")
