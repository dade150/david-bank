from datetime import UTC, datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api import account, advice, agent, auth, categorize, chat, glossary, ingest
from src.config import settings
from src.exception import AppError

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
    # logger.exception(exc) in G7
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