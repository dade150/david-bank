from pathlib import Path

from src.llm.client import LLMProvider
from src.llm.embedding_client import EmbeddingClient
from src.llm.types import Message
from src.services.retrieval_service import RetrievalService
from src.types.advice import AdviceRequest, AdviceResponse, Citation

ADVICE_SYSTEM = (Path(__file__).parent.parent / "prompts" / "chat_system_v1.md").read_text()

# Rifiuto deterministico: nessuna chiamata LLM, nessuna citazione.
# Scatta quando il retrieval (già filtrato per soglia e per ruolo) non torna nulla.
REFUSAL_ANSWER = (
    "Non trovo questa informazione nei documenti di LipariBank. "
    "Posso aiutarti con qualcos'altro?"
)


class RAGService:
    def __init__(
        self,
        retrieval: RetrievalService,
        llm: LLMProvider,
        embedding_client: EmbeddingClient,
    ) -> None:
        self.retrieval = retrieval
        self.llm = llm
        self.embedding_client = embedding_client

    async def answer(self, req: AdviceRequest, username: str, role: str) -> AdviceResponse:
        # 1. Vettorizza la domanda
        query_vec = await self.embedding_client.embed_one(req.question)

        # 2. Retrieval con soglia, visibility E appartenenza:
        #    chunks vuoto => rifiuto, stop qui, nessuna chiamata LLM.
        chunks = await self.retrieval.search_for_user(
            query_vec, username=username, role=role, top_k=5,
        )

        if not chunks:
            return AdviceResponse(
                answer=REFUSAL_ANSWER,
                citations=[],
                tokens_used=0,
                cost_eur=0,
            )

        # 3. Build context string
        context_parts = [
            f"[{c.document_id}, {c.chunk_id}, sim:{c.similarity:.2f}]\n{c.content}"
            for c in chunks
        ]
        context = "\n\n---\n\n".join(context_parts)

        # 4. Generate
        user_prompt = f"""CONTESTI:
            {context}

        DOMANDA: {req.question}

        RISPOSTA (con citazioni):"""

        llm_response = await self.llm.complete(
            messages=[
                Message(role="system", content=ADVICE_SYSTEM),
                Message(role="user", content=user_prompt),
            ],
            max_tokens=800,
        )

        # 5. Build citations from retrieved chunks
        citations = [
            Citation(
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                excerpt=c.content[:200] + "..." if len(c.content) > 200 else c.content,
                similarity=c.similarity,
            )
            for c in chunks
        ]

        return AdviceResponse(
            answer=llm_response.content,
            citations=citations,
            tokens_used=llm_response.tokens_used,
            cost_eur=llm_response.cost_eur,
        )
