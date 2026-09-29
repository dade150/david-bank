# src/db/models.py
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_naive)
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    model_used: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_naive)
    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class Account(Base):
    __tablename__ = "accounts"
    iban: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    movements: Mapped[list["Movement"]] = relationship(back_populates="account")


class Movement(Base):
    __tablename__ = "movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_iban: Mapped[str] = mapped_column(String, ForeignKey("accounts.iban"), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Decimale per evitare errori sui centesimi
    account: Mapped["Account"] = relationship(back_populates="movements")

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(String, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    chunk_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    visibility: Mapped[str] = mapped_column(String(32), default="public", index=True)
    # Appartenenza: None = documento centrale, visibile a tutte le filiali.
    branch_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # Dichiarato qui perché Alembic lo tenga: era già stato droppato per assenza.
    __table_args__ = (
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="operator")
    # Filiale di appartenenza: None = funzione centrale senza filiale propria.
    branch_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

class ComplianceAlert(Base):
    __tablename__ = "compliance_alerts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    account_iban: Mapped[str] = mapped_column(ForeignKey("accounts.iban"), index=True)
    opened_by: Mapped[str] = mapped_column(String(64))       # username dal token
    reason: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

class Card(Base):
    __tablename__ = "cards"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    account_iban: Mapped[str] = mapped_column(ForeignKey("accounts.iban"), index=True)
    last4: Mapped[str] = mapped_column(String(4))            # ultime 4 cifre, mai il PAN
    tipo: Mapped[str] = mapped_column(String(32))            # debito | credito
    stato: Mapped[str] = mapped_column(String(32))           # attiva | bloccata | da_attivare
    limite: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

class Transfer(Base):
    __tablename__ = "transfers"
    # codice leggibile (TRF-2026-0001): è l'identificativo che il cliente cita allo sportello
    riferimento: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_iban: Mapped[str] = mapped_column(ForeignKey("accounts.iban"), index=True)
    destinatario: Mapped[str] = mapped_column(String(64))
    importo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stato: Mapped[str] = mapped_column(String(32))           # accreditato | in_elaborazione | rifiutato
    data: Mapped[datetime] = mapped_column(DateTime, nullable=False)

JSON_O_JSONB = JSON().with_variant(JSONB(), "postgresql")    # JSONB su Postgres, JSON nei test

class AgentRunState(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)      # il run_id del Giorno 7
    username: Mapped[str] = mapped_column(String(64), index=True)      # chi ha chiesto
    role: Mapped[str] = mapped_column(String(32))                      # i tool si rifanno per lui
    status: Mapped[str] = mapped_column(String(32), index=True)
    # awaiting_approval | running | done | rejected
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON_O_JSONB)   # ← lo stato
    pending_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON_O_JSONB)
    description: Mapped[str] = mapped_column(Text)                     # cosa si sta approvando
    steps: Mapped[int] = mapped_column(Integer)
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    tool_calls: Mapped[list[str]] = mapped_column(JSON_O_JSONB)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )