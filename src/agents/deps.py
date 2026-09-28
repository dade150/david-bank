from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.repos import (
    AccountAccess,
    AlertRepository,
    CardAccess,
    MovementAccess,
    TransferAccess,
)
from src.db.session import get_db
from src.llm.embedding_client import EmbeddingClient
from src.llm.opencode_provider import OpencodeProvider
from src.services.retrieval_service import RetrievalService


@dataclass(frozen=True)
class Deps:
    """Tutto ciò di cui un passo dell'agente ha bisogno, per una singola richiesta."""

    session: AsyncSession
    accounts: AccountAccess
    movements: MovementAccess
    cards: CardAccess
    transfers: TransferAccess
    alerts: AlertRepository
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


def get_deps(db: Annotated[AsyncSession, Depends(get_db)]) -> Deps:
    embedder = EmbeddingClient()
    return Deps(
        session=db,
        accounts=AccountAccess(db),
        movements=MovementAccess(db),
        cards=CardAccess(db),
        transfers=TransferAccess(db),
        alerts=AlertRepository(db),
        retrieval=RetrievalService(db, embedder),
        embedder=embedder,
        provider=_provider(),
    )
