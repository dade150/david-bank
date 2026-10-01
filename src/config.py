import sys
from decimal import Decimal

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LipariBank AI"
    debug: bool = False

    database_url: str
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    opencode_api_key: str = ""
    opencode_base_url: str = "http://localhost:4096"
    opencode_server_username: str = "opencode"
    opencode_server_password: str = ""
    default_model: str = "opencode/mimo-v2.6-flash-free"
    embedding_model: str = "text-embedding-3-small"
    max_tokens_per_request: int = 2000
    min_similarity: float = 0.30
    jwt_secret: str
    redis_url: str = ""

    # Agente (Giorno 7): il loop parla col server opencode locale
    # (stesso che usano chat e advice), con i modelli gratuiti inclusi.
    agent_model: str = "opencode/mimo-v2.6-flash-free"
    agent_max_steps: int = 6

    # Approvazioni (Giorno 8): sopra questa cifra un tool che scrive decide una persona.
    # Non sta nel prompt né nel codice: sta qui, così cambia senza ripubblicare.
    soglia_approvazione_eur: Decimal = Decimal(5000)


try:
    # i campi obbligatori (database_url, jwt_secret) arrivano dall'env: mypy non lo sa
    settings = Settings()  # type: ignore[call-arg]
except ValidationError as e:
    print("\n❌ Errore critico all'avvio: Configurazione mancante o errata.")
    print("Controlla il tuo file .env per questi campi:")

    for error in e.errors():
        campo = str(error["loc"][0]).upper()
        messaggio = error["msg"]
        print(f"  -> {campo}: {messaggio}")

    print("\nL'applicazione verrà terminata.\n")
    sys.exit(1)
