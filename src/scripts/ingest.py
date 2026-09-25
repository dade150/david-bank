# scripts/ingest_docs.py
import asyncio
import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"

# Appartenenza per documento: id -> (visibility, branch_id).
# I documenti non elencati restano public e centrali (branch_id None).
APPARTENENZA: dict[str, tuple[str, str | None]] = {
    "info_riservate_milano": ("internal", "MI-01"),
}


async def main() -> None:
    # Con --reset svuota tutto prima di ricaricare: un solo comando ripopola da zero.
    do_reset = "--reset" in sys.argv

    docs_dir = Path("data/docs")
    percorsi = await asyncio.to_thread(lambda: sorted(docs_dir.glob("*.md")))
    async with httpx.AsyncClient(timeout=60.0) as client:
        if do_reset:
            r = await client.post(f"{BASE_URL}/api/ai/documents/reset")
            print(f"reset: {r.json()}")

        for path in percorsi:
            # leggere un file è bloccante: dentro una coroutine si sposta su un thread
            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
            visibility, branch_id = APPARTENENZA.get(path.stem, ("public", None))
            response = await client.post(
                f"{BASE_URL}/api/ai/documents/ingest",
                json={
                    "document_id": path.stem,
                    "content": content,
                    "metadata": {"source": str(path), "title": path.stem.replace("_", " ")},
                    "visibility": visibility,
                    "branch_id": branch_id,
                },
            )
            print(f"{path.name}: {response.json()} (visibility={visibility}, branch={branch_id})")


if __name__ == "__main__":
    asyncio.run(main())