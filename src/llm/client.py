from typing import Protocol

from src.llm.llm_types import LLMResponse, Message


class LLMProvider(Protocol):
    async def complete(
        self, messages: list[Message], max_tokens: int = 500
    ) -> LLMResponse: ...
