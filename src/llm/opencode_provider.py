import base64

from opencode_ai import AsyncOpencode
from opencode_ai.types import TextPartInputParam

from src.llm.types import LLMResponse, Message


class OpencodeProvider:
    """Provider per il server locale di opencode (modelli gratuiti inclusi)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "opencode/mimo-v2.6-flash-free",
        base_url: str = "http://localhost:4096",
        username: str = "opencode",
        password: str = "",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.username = username
        self.password = password

    def _split_model(self) -> tuple[str, str]:
        if "/" in self.model:
            provider_id, model_id = self.model.split("/", 1)
            return provider_id, model_id
        return "opencode", self.model

    def _client(self) -> AsyncOpencode:
        headers: dict[str, str] = {}
        if self.password:
            token = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {token}"
        return AsyncOpencode(base_url=self.base_url, default_headers=headers)

    async def complete(
        self, messages: list[Message], max_tokens: int = 500
    ) -> LLMResponse:
        client = self._client()
        session = await client.session.create()
        provider_id, model_id = self._split_model()

        system_text = "\n\n".join(
            m.content for m in messages if m.role == "system"
        )
        dialog = "\n\n".join(
            f"{m.role}:\n{m.content}" for m in messages if m.role != "system"
        )

        # Il body del server vuente `model: {providerID, modelID}`,
        # non i campi piatti generati dallo SDK.
        chat_kwargs: dict = {
            "id": session.id,
            "model_id": model_id,
            "provider_id": provider_id,
            "parts": [TextPartInputParam(type="text", text=dialog)],
            "extra_body": {
                "model": {"providerID": provider_id, "modelID": model_id}
            },
        }
        if system_text:
            chat_kwargs["system"] = system_text

        response = await client.session.chat(**chat_kwargs)
        data = response.model_dump()
        info = data.get("info") or data
        parts = data.get("parts") or []
        content = "".join(
            p.get("text", "") for p in parts if p.get("type") == "text"
        )

        error = info.get("error")
        if error and not content:
            message = (error.get("data") or {}).get("message", str(error))
            raise RuntimeError(f"opencode chat failed: {message}")

        tokens = info.get("tokens") or {}
        input_tokens = int(tokens.get("input") or 0)
        output_tokens = int(tokens.get("output") or 0)
        cost = float(info.get("cost") or 0.0)

        return LLMResponse(
            content=content,
            tokens_used=input_tokens + output_tokens,
            cost_eur=cost,
            model=self.model,
        )
