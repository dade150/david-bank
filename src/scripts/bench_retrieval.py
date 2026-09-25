"""Confronto PRIMA / DOPO del filtro di appartenenza, sui dati reali nel db.

PRIMA  = query di Giorno 6: WHERE visibility = ANY(:livelli)
DOPO   = query di Estensione 2: JOIN su app_users + branch_id nel WHERE

    uv run python -m src.scripts.bench_retrieval --runs 20
"""
import argparse
import asyncio
import statistics
import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from src.config import settings
from src.db.models import DocumentChunk
from src.db.session import AsyncSessionLocal
from src.llm.embedding_client import EmbeddingClient
from src.services.retrieval_service import (
    RetrievalService,
    visible_to,
)

QUERY = "quali sono le commissioni dei bonifici esteri?"


async def time_query(session: AsyncSession, sql: TextClause, params: dict[str, Any],
                     runs: int) -> list[float]:
    tempi: list[float] = []
    for i in range(runs + 1):  # la prima e' warmup
        t0 = time.perf_counter()
        result = await session.execute(sql, params)
        rows = result.fetchall()
        dt = (time.perf_counter() - t0) * 1000
        if i > 0:
            tempi.append(dt)
        elif not rows:
            raise SystemExit("query senza risultati: abbassare la soglia o controllare i dati")
    return tempi


async def explain(session: AsyncSession, sql: TextClause, params: dict[str, Any],
                  label: str) -> None:
    result = await session.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + str(sql)),
                                   params)
    lines = [r[0] for r in result.fetchall()]
    print(f"\n--- EXPLAIN {label} ---")
    for line in lines:
        if any(k in line for k in ("Execution Time", "actual time", "Seq Scan",
                                   "Index Scan", "Bitmap", "Hash Join",
                                   "Nested Loop")):
            print(f"  {line.strip()}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    embedding = EmbeddingClient()
    query_vec = await embedding.embed_one(QUERY)

    async with AsyncSessionLocal() as session:
        totale = await session.scalar(select(func.count()).select_from(DocumentChunk))
        print(f"chunk totali nel db: {totale}")
        print(f"query: {QUERY!r}  soglia={settings.min_similarity}")

        livelli = visible_to("operator")
        params_prima = {"q": str(query_vec), "k": 5,
                        "soglia": settings.min_similarity, "livelli": livelli}
        params_dopo = {**params_prima, "username": "mbianchi"}

        # PRIMA = DOPO senza la parte di appartenenza (stessi parametri, in piu'
        # username che la PRIMA non usa): il delta e' il costo della estensione.
        tempi_prima = await time_query(session, RetrievalService.SQL_PRIMA,
                                       params_prima, args.runs)
        tempi_dopo = await time_query(session, RetrievalService.SQL_PER_RUOLO,
                                      params_dopo, args.runs)

        righe_prima = (await session.execute(RetrievalService.SQL_PRIMA,
                                             params_prima)).fetchall()
        righe_dopo = (await session.execute(RetrievalService.SQL_PER_RUOLO,
                                            params_dopo)).fetchall()

        def stats(tempi: list[float]) -> str:
            return (f"media {statistics.mean(tempi):7.2f} ms   "
                    f"mediana {statistics.median(tempi):7.2f} ms   "
                    f"max {max(tempi):7.2f} ms")

        print(f"\nPRIMA (visibility)        {stats(tempi_prima)}")
        print(f"DOPO  (visibility+branch) {stats(tempi_dopo)}")
        delta = statistics.mean(tempi_dopo) - statistics.mean(tempi_prima)
        pct = 100 * delta / statistics.mean(tempi_prima)
        print(f"\ndelta medio: {delta:+.2f} ms ({pct:+.1f}%)")
        print(f"righe PRIMA: {len(righe_prima)}  righe DOPO (mbianchi MI-01): "
              f"{len(righe_dopo)}")

        await explain(session, RetrievalService.SQL_PRIMA, params_prima, "PRIMA")
        await explain(session, RetrievalService.SQL_PER_RUOLO, params_dopo, "DOPO")


if __name__ == "__main__":
    asyncio.run(main())
