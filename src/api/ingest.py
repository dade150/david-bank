from fastapi import APIRouter, Depends
from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk
from src.db.session import get_db
from src.llm.embedding_client import EmbeddingClient
from src.services.ingest_service import IngestService
from src.types.advice import IngestRequest, IngestResponse

router = APIRouter(prefix="/api/ai", tags=["Chat"])

@router.post(
    "/documents/ingest",
    response_model=IngestResponse,
    summary="Ingest document into vector store",
)
async def ingest_document(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    embedding_client = EmbeddingClient()
    service = IngestService(db, embedding_client)
    chunk_count = await service.ingest_document(
        document_id=req.document_id,
        content=req.content,
        metadata=req.metadata,
        visibility=req.visibility,
        branch_id=req.branch_id,
    )
    return IngestResponse(chunk_count=chunk_count, embedding_dim=embedding_client.dim)


@router.post(
    "/documents/reset",
    summary="Delete all ingested chunks (repopulate from scratch)",
)
async def reset_documents(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(delete(DocumentChunk))
    await db.commit()
    # rowcount esiste su CursorResult, non su Result in generale
    deleted = result.rowcount if isinstance(result, CursorResult) else 0
    return {"deleted_rows": deleted or 0}


@router.get(
    "/documents/stats",
    summary="Chunk count per document",
)
async def documents_stats(db: AsyncSession = Depends(get_db)) -> dict:
    stmt = (
        select(DocumentChunk.document_id, func.count().label("chunks"))
        .group_by(DocumentChunk.document_id)
        .order_by(DocumentChunk.document_id)
    )
    rows = (await db.execute(stmt)).all()
    return {"documents": {row.document_id: row.chunks for row in rows}}