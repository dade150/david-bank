import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api import account, advice, agent, auth, categorize, chat, glossary, ingest
from src.config import settings
from src.exception import AppError

# Senza questa riga il root logger resta a WARNING: tutti i logger.info
# dell'agente (agent_step, con run_id e step) non finiscono in nessun file.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


class _ConExtra(logging.Formatter):
    """Anche i campi passati con `extra=` nella riga di log.

    Senza, `run_id`, `tool`, `tool_args` restano nel record ma non sul file:
    e sono la traccia che leggi dopo per capire cosa è successo in un run.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        campi = {
            k: v for k, v in record.__dict__.items()
            if k not in _STANDARD and not k.startswith("_")
        }
        if not campi:
            return base
        dettagli = " ".join(f"{k}={v}" for k, v in campi.items())
        return f"{base} {dettagli}"


_STANDARD = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}

for _h in logging.getLogger().handlers:
    _h.setFormatter(_ConExtra("%(asctime)s %(levelname)s %(name)s %(message)s"))

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Bootcamp Python AI Powered v1",
)


@app.exception_handler(AppError)
async def handle_app_error(req: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status": exc.status_code,
            "error": exc.code,
            "message": exc.message,
            "path": req.url.path,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(req: Request, exc: Exception) -> JSONResponse:
    logger.exception("errore non gestito su %s", req.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status": 500,
            "error": "INTERNAL_ERROR",
            "message": "Errore inatteso",
            "path": req.url.path,
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "UP"}

app.include_router(chat.router)
app.include_router(categorize.router)
app.include_router(glossary.router)
app.include_router(account.router)
app.include_router(ingest.router)
app.include_router(advice.router)
app.include_router(agent.router)
app.include_router(auth.router)