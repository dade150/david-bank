from openai import AsyncOpenAI

from src.llm.types import LLMResponse, Message

# USD per 1M token (input, output) — https://openai.com/api/pricing/
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5": (1.25, 10.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
}
USD_TO_EUR = 0.92


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    def _cost_eur(self, prompt_tokens: int, completion_tokens: int) -> float:
        in_price, out_price = PRICING.get(self.model, (0.0, 0.0))
        usd = (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000
        return round(usd * USD_TO_EUR, 6)

    async def complete(
        self, messages: list[Message], max_tokens: int = 500
    ) -> LLMResponse:
        payload = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("system", "user", "assistant")
        ]
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=payload,  # type: ignore[arg-type]
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        return LLMResponse(
            content=choice.message.content or "",
            tokens_used=prompt_tokens + completion_tokens,
            cost_eur=self._cost_eur(prompt_tokens, completion_tokens),
            model=self.model,
        )
