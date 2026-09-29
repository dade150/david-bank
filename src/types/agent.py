from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AgentResponse(BaseModel):
    run_id: str
    reply: str
    steps: int
    tool_calls: list[str]
    stopped_by: str        # "model" | "max_steps" | "budget" | "awaiting_approval"
    cost_eur: float


class RunStatus(BaseModel):
    """Cosa sta per essere approvato: ciò che legge chi decide, e nient'altro."""

    run_id: str
    status: str            # awaiting_approval | running | done | rejected
    requested_by: str
    description: str
    decided_by: str | None


class RejectRequest(BaseModel):
    motivo: str = Field(min_length=10, max_length=500)


class SupervisorResponse(BaseModel):
    risposta: str
    instradamento: str                              # "dati_conto" | "policy" | "entrambi"
    specialisti_completi: dict[str, bool]
    cost_eur: float
