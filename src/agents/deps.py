from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.repos import (
    AccountAccess,
    CardAccess,
    MovementAccess,
    TransferAccess,
)
from src.db.runs import RunRepository
from src.db.session import get_db
from src.llm.embedding_client import EmbeddingClient
from src.llm.opencode_provider import OpencodeProvider
from src.services.alerts import AlertService
from src.services.retrieval_service import RetrievalService


@dataclass(frozen=True)
class Deps:
    """Tutto ciò di cui un passo dell'agente ha bisogno, per una singola richiesta."""

    session: AsyncSession
    accounts: AccountAccess
    movements: MovementAccess
    cards: CardAccess
    transfers: TransferAccess
    alerts: AlertService
    runs: RunRepository          # Giorno 8: dove un run sospeso aspetta
    retrieval: RetrievalService
    embedder: EmbeddingClient
    provider: OpencodeProvider


@lru_cache(maxsize=1)
def _provider() -> OpencodeProvider:
    """Un solo provider per tutto il processo: il server opencode è locale."""
    return OpencodeProvider(
        model=settings.agent_model,
        base_url=settings.opencode_base_url,
        username=settings.opencode_server_username,
        password=settings.opencode_server_password,
    )


def crea_deps(
    db: AsyncSession,
    *,
    embedder: EmbeddingClient | None = None,
    provider: OpencodeProvider | None = None,
) -> Deps:
    """I servizi su una sessione. La usano l'endpoint e, al Giorno 8, il server MCP."""
    embedder = embedder or EmbeddingClient()      # uno solo per richiesta, usato da due
    return Deps(
        session=db,
        accounts=AccountAccess(db),
        movements=MovementAccess(db),
        cards=CardAccess(db),
        transfers=TransferAccess(db),
        alerts=AlertService(db),
        runs=RunRepository(db),
        retrieval=RetrievalService(db, embedder),
        embedder=embedder,
        provider=provider or _provider(),
    )


def get_deps(db: Annotated[AsyncSession, Depends(get_db)]) -> Deps:
    return crea_deps(db)
