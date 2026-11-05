from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.database.models.chat_message import ChatMessage
    from app.database.models.document_chunk import DocumentChunk


class MessageCitation(CreatedAtMixin, Base):
    __tablename__ = "message_citations"
    __table_args__ = (
        UniqueConstraint("message_id", "citation_index", name="message_citation_index"),
    )

    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    citation_index: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text)

    message: Mapped[ChatMessage] = relationship(back_populates="citations")
    chunk: Mapped[DocumentChunk] = relationship(back_populates="citations")
