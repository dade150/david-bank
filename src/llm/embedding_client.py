from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer("all-MiniLM-L6-v2")

class EmbeddingClient:
    def __init__(self) -> None:
        self._model = _get_model()
        self.dim = 384

    def _encode(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        return await asyncio.to_thread(self._encode, texts)

    async def embed_one(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result[0]