from anthropic import AsyncAnthropic

from src.llm.types import LLMResponse, Message

# USD per 1M token (input, output) — https://www.anthropic.com/pricing
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
}
USD_TO_EUR = 0.92


class AnthropicProvider:
    """Gemello di OpenAIProvider: stessa firma, tre differenze API.

    1. Il prompt di sistema non è un messaggio: va nel parametro `system`.
    2. I campi consumo si chiamano `input_tokens` / `output_tokens`.
    3. I messaggi ammettono solo ruoli `user` e `assistant` (niente `system`).
    """

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    def _cost_eur(self, input_tokens: int, output_tokens: int) -> float:
        in_price, out_price = PRICING.get(self.model, (0.0, 0.0))
        usd = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
        return round(usd * USD_TO_EUR, 6)

    async def complete(
        self, messages: list[Message], max_tokens: int = 500
    ) -> LLMResponse:
        system_text = "\n\n".join(
            m.content for m in messages if m.role == "system"
        )
        chat_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        kwargs: dict = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        if system_text:
            kwargs["system"] = system_text
        response = await self.client.messages.create(**kwargs)
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        return LLMResponse(
            content=text,
            tokens_used=input_tokens + output_tokens,
            cost_eur=self._cost_eur(input_tokens, output_tokens),
            model=self.model,
        )
