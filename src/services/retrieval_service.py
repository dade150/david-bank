import logging

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm.embedding_client import EmbeddingClient

logger = logging.getLogger(__name__)

# Livelli di visibility che ogni ruolo può leggere.
# Il ruolo sconosciuto vede solo "public": si amplia per default, mai per errore.
VISIBILITA_PER_RUOLO: dict[str, list[str]] = {
    "operator": ["public", "internal"],
    "compliance_lead": ["public", "internal", "compliance_only"],
    "risk_lead": ["public", "internal", "risk_only"],
}


def visible_to(role: str) -> list[str]:
    livelli = VISIBILITA_PER_RUOLO.get(role)
    if livelli is None:
        logger.warning(
            "ruolo non riconosciuto %r nel token: accesso limitato ai documenti public",
            role,
        )
        return ["public"]
    return livelli


class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    similarity: float
    metadata: dict


class RetrievalService:
    # Il filtro di permesso sta nel WHERE, dentro la stessa query della ricerca
    # approssimata: il LIMIT agisce su ciò che l'utente può vedere, non su tutto
    # il corpus. Filtrare dopo il recupero significherebbe pagare la soglia e il
    # limite su righe che poi scarteremmo.
    #
    # La JOIN su app_users porta la filiale dell'utente dentro la stessa riga
    # della query: il token non la contiene (sub, role, exp e basta), quindi o la
    # leggiamo qui o con una query a parte. La scelta qui costa un cambio di
    # piano, ed e' quello che il bench misura.
    SQL_PER_RUOLO = text("""
        SELECT c.id, c.document_id, c.content, c.chunk_metadata,
               1 - (c.embedding <=> CAST(:q AS vector)) AS similarity
        FROM document_chunks c
        JOIN app_users u ON u.username = :username
        WHERE 1 - (c.embedding <=> CAST(:q AS vector)) >= :soglia
          AND c.visibility = ANY(:livelli)
          AND (c.branch_id IS NULL            -- documento centrale: lo vedono tutti
               OR u.branch_id IS NULL         -- utente centrale: vede tutte le filiali
               OR c.branch_id = u.branch_id)  -- stessa filiale
        ORDER BY c.embedding <=> CAST(:q AS vector)
        LIMIT :k
    """)

    # Senza utente (ingestione, script, bench): nessuna appartenenza, solo soglia.
    SQL_SENZA_RUOLO = text("""
        SELECT c.id, c.document_id, c.content, c.chunk_metadata,
               1 - (c.embedding <=> CAST(:q AS vector)) AS similarity
        FROM document_chunks c
        WHERE 1 - (c.embedding <=> CAST(:q AS vector)) >= :soglia
        ORDER BY c.embedding <=> CAST(:q AS vector)
        LIMIT :k
    """)

    # Solo visibility, senza la parte di appartenenza: e' la query di prima
    # l'estensione, tenuta qui per il confronto nel bench.
    SQL_PRIMA = text("""
        SELECT c.id, c.document_id, c.content, c.chunk_metadata,
               1 - (c.embedding <=> CAST(:q AS vector)) AS similarity
        FROM document_chunks c
        WHERE 1 - (c.embedding <=> CAST(:q AS vector)) >= :soglia
          AND c.visibility = ANY(:livelli)
        ORDER BY c.embedding <=> CAST(:q AS vector)
        LIMIT :k
    """)

    def __init__(self, session: AsyncSession, embedding_client: EmbeddingClient) -> None:
        self.session = session
        self.embedding_client = embedding_client

    async def search_for_user(
        self, query_vec: list[float], username: str, role: str, top_k: int = 5,
    ) -> list[RetrievalResult]:
        """I passaggi più vicini FRA QUELLI che questo utente può vedere."""
        result = await self.session.execute(
            self.SQL_PER_RUOLO,
            {
                "q": str(query_vec),
                "k": top_k,
                "soglia": settings.min_similarity,
                "livelli": visible_to(role),
                "username": username,
            },
        )
        return [self._to_result(row) for row in result.fetchall()]

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Ricerca per testo senza utente: ingestione e script."""
        query_vec = await self.embedding_client.embed_one(query)
        return await self.search_with_vector(query_vec, top_k=top_k)

    async def search_with_vector(
        self, query_vec: list[float], top_k: int = 5,
    ) -> list[RetrievalResult]:
        result = await self.session.execute(
            self.SQL_SENZA_RUOLO,
            {"q": str(query_vec), "k": top_k, "soglia": settings.min_similarity},
        )
        return [self._to_result(row) for row in result.fetchall()]

    @staticmethod
    def _to_result(row) -> RetrievalResult:
        return RetrievalResult(
            chunk_id=str(row.id),
            document_id=row.document_id,
            content=row.content,
            similarity=float(row.similarity),
            metadata=row.chunk_metadata,
        )
