from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repos import ChatRepository
from src.exception import ChatSessionNotFoundError
from src.llm.client import LLMProvider
from src.llm.llm_types import Message
from src.types.chat import ChatRequest, ChatResponse


class ChatService:
    def __init__(
        self, session: AsyncSession, llm: LLMProvider, system_prompt: str
    ) -> None:
        self.session = session
        self.repo = ChatRepository(session)
        self.llm = llm
        self.system_prompt = system_prompt

    async def chat(self, req: ChatRequest, user_id: str) -> ChatResponse:
        """Una risposta del modello, con la conversazione ricostruita e persistita.

        Solleva ChatSessionNotFoundError se la sessione richiesta non esiste.
        Quando ritorna, nel database ci sono due messaggi in più e la transazione è chiusa.
        """
        if req.session_id == "new":
            chat_session = await self.repo.create_session(user_id=user_id)
        else:
            trovata = await self.repo.find_session(req.session_id)
            if trovata is None:
                raise ChatSessionNotFoundError(req.session_id)
            chat_session = trovata

        # La storia va letta PRIMA di aggiungere il messaggio nuovo
        history = await self.repo.list_messages(chat_session.id)

        messages: list[Message] = [Message(role="system", content=self.system_prompt)]
        for m in history:
            messages.append(Message(role=m.role, content=m.content))  # type: ignore[arg-type]
        messages.append(Message(role="user", content=req.message))

        llm_response = await self.llm.complete(messages, max_tokens=500)

        await self.repo.add_message(
            session_id=chat_session.id,
            role="user",
            content=req.message,
            tokens=0,
            cost_eur=Decimal(0),
            model_used=llm_response.model,
        )
        await self.repo.add_message(
            session_id=chat_session.id,
            role="assistant",
            content=llm_response.content,
            tokens=llm_response.tokens_used,
            cost_eur=Decimal(str(llm_response.cost_eur)),
            model_used=llm_response.model,
        )

        await self.session.commit()

        return ChatResponse(
            session_id=chat_session.id,
            reply=llm_response.content,
            token_used=llm_response.tokens_used,
            cost=llm_response.cost_eur,
            model_used=llm_response.model,
            created_at=datetime.now(UTC),
        )