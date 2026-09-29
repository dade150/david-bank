from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class Tool:
    """Un tool esposto al modello: contratto pubblico più implementazione."""

    name: str
    description: str
    args_model: type[BaseModel]
    run: Callable[[Any], Awaitable[str]]
    scrive: bool = True  # chi non lo dichiara è trattato come chi scrive
    # Solo per chi scrive: dice, dagli argomenti validati, se serve l'approvazione.
    # None vuol dire «sempre»: il tool nuovo che nessuno ha pensato è protetto.
    serve_approvazione: Callable[[Any], bool] | None = None

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }