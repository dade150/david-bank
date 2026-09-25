from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.llm.factory import get_llm_provider
from src.services.chat_service import ChatService
from src.types.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/ai", tags=["Chat"])

SYSTEM_PROMPT = (
    Path(__file__).parent.parent / "prompts" / "chat_system_v1.md"
).read_text(encoding="utf-8")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    service = ChatService(db, get_llm_provider(), SYSTEM_PROMPT)
    return await service.chat(req, user_id="dummy-user")
