from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.database.models.document_chunk import DocumentChunk


class SourceDocument(TimestampMixin, Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("ticker", "accession_number", name="ticker_accession"),)

    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(20), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
