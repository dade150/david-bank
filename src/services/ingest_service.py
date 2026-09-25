from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk
from src.llm.chunking import chunk_text
from src.llm.embedding_client import EmbeddingClient


class IngestService:
    def __init__(self, session: AsyncSession, embedding_client: EmbeddingClient) -> None:
        self.session = session
        self.embedding_client = embedding_client

    async def ingest_document(
        self,
        document_id: str,
        content: str,
        metadata: dict | None = None,
        visibility: str = "public",
        branch_id: str | None = None,
    ) -> int:
        # Replace, non append: ricaricare lo stesso document_id non raddoppia i chunk.
        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )

        # Dedup: se lo stesso testo compare due volte (es. pagina ripetuta nel PDF),
        # resta un solo chunk e quindi una sola citazione.
        seen: set[str] = set()
        chunks: list[str] = []
        for chunk in chunk_text(content, 500, 50):
            if chunk not in seen:
                seen.add(chunk)
                chunks.append(chunk)

        embeddings = await self.embedding_client.embed(chunks) if chunks else []

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            db_chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=idx,
                content=chunk,
                embedding=embedding,
                chunk_metadata=metadata or {},
                visibility=visibility,
                branch_id=branch_id,
            )
            self.session.add(db_chunk)

        await self.session.commit()
        return len(chunks)