from src.config import settings
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.client import LLMProvider
from src.llm.openai_provider import OpenAIProvider
from src.llm.opencode_provider import OpencodeProvider


def get_llm_provider(model: str | None = None) -> LLMProvider:
    selected = model or settings.default_model
    if selected.startswith("gpt"):
        return OpenAIProvider(settings.openai_api_key, selected)
    elif selected.startswith("claude"):
        return AnthropicProvider(settings.anthropic_api_key, selected)
    elif selected.startswith(("opencode", "mimo")):
        return OpencodeProvider(
            settings.opencode_api_key,
            selected,
            base_url=settings.opencode_base_url,
            username=settings.opencode_server_username,
            password=settings.opencode_server_password,
        )
    else:
        raise ValueError(f"Unknown model: {selected}")
