from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import UserContext, get_current_user
from src.db.session import get_db
from src.llm.embedding_client import EmbeddingClient
from src.llm.factory import get_llm_provider
from src.services.rag_service import RAGService
from src.services.retrieval_service import RetrievalService
from src.types.advice import AdviceRequest, AdviceResponse

router = APIRouter(prefix="/api/ai", tags=["Chat"])


@router.post("/advice", response_model=AdviceResponse, summary="Get banking advice with RAG",
    description="Retrieval Augmented Generation con citazioni.")
async def advice(
    req: AdviceRequest,
    user: Annotated[UserContext, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> AdviceResponse:
    """Costruisce i servizi per QUESTA richiesta e delega. Nessuna logica qui dentro."""
    embedding_client = EmbeddingClient()
    retrieval = RetrievalService(db, embedding_client)
    llm = get_llm_provider()
    rag = RAGService(retrieval, llm, embedding_client)
    return await rag.answer(req, username=user.username, role=user.role)
