from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable

from app.database.models import Base, DocumentChunk, User


def test_all_models_are_registered() -> None:
    configure_mappers()

    assert set(Base.metadata.tables) == {
        "users",
        "source_documents",
        "document_chunks",
        "chat_threads",
        "chat_messages",
        "message_citations",
    }
    assert User.__table__.c.id.default is None


def test_document_chunks_use_postgres_vector_and_generated_search_vector() -> None:
    embedding = DocumentChunk.__table__.c.embedding
    search_vector = DocumentChunk.__table__.c.search_vector
    indexes = {index.name: index for index in DocumentChunk.__table__.indexes}
    ddl = str(CreateTable(DocumentChunk.__table__).compile(dialect=postgresql.dialect())).casefold()

    assert embedding.type.dim == 1536
    assert search_vector.computed is not None
    assert {
        "ix_document_chunks_embedding_hnsw",
        "ix_document_chunks_search_vector_gin",
    } <= indexes.keys()
    assert (
        indexes["ix_document_chunks_embedding_hnsw"].dialect_options["postgresql"]["using"]
        == "hnsw"
    )
    assert (
        indexes["ix_document_chunks_search_vector_gin"].dialect_options["postgresql"]["using"]
        == "gin"
    )
    assert "vector(1536)" in ddl
    assert "generated always as" in ddl
    assert "to_tsvector('english', content)" in ddl
