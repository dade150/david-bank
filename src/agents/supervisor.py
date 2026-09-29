# src/agents/supervisor.py — un triage piccolo, due specialisti, una sintesi che non inventa
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from src.agents.deps import Deps
from src.agents.loop import costo_eur, run_agent
from src.agents.prompts import (
    PROMPT_DATI_CONTO,
    PROMPT_POLICY,
    PROMPT_SINTESI,
    PROMPT_TRIAGE,
)
from src.agents.tools import build_tools_for
from src.auth.deps import UserContext
from src.config import settings
from src.llm.llm_types import Message

# Il triage è una classificazione, non un agente: costa quel che costa il modello
# che usiamo per tutto il resto. Con un solo modello in .env, qui non se ne sceglie uno.
INSTRADAMENTO: dict[str, tuple[str, ...]] = {
    "dati_conto": ("dati_conto",),
    "policy": ("policy",),
    "entrambi": ("dati_conto", "policy"),
}


@dataclass(frozen=True)
class Specialista:
    nome: Literal["dati_conto", "policy"]
    system_prompt: str
    tool_names: tuple[str, ...]


SPECIALISTI = {
    "dati_conto": Specialista(
        "dati_conto", PROMPT_DATI_CONTO,
        # nessun find_customer_accounts: in questo modello i conti si chiedono per IBAN
        ("get_account_balance", "list_recent_movements"),
    ),
    "policy": Specialista("policy", PROMPT_POLICY, ("search_documents",)),
}


class Contributo(BaseModel):
    """Quello che uno specialista consegna: dati che il codice sa, non impressioni."""

    specialista: Literal["dati_conto", "policy"]
    completo: bool            # ha risposto il modello, non il tetto: lo dice stopped_by
    stopped_by: str
    contenuto: str
    tool_calls: list[str]


@dataclass
class SupervisorResult:
    risposta: str
    instradamento: str
    contributi: list[Contributo]
    cost_eur: Decimal


async def run_supervisor(
    user: UserContext, domanda: str, deps: Deps
) -> SupervisorResult:
    """Sceglie chi deve rispondere, li fa lavorare ognuno col suo tool, e ricompone."""
    costo = Decimal(0)

    # 1. il triage: una chiamata, un insieme chiuso di risposte. Non è un agente, è
    #    una classificazione; e se risponde altro, si prende la strada più prudente
    triage = await deps.provider.complete([
        Message(role="system", content=PROMPT_TRIAGE),
        Message(role="user", content=domanda),
    ])
    costo += costo_eur(triage.cost_eur)
    scelta = triage.content.strip().lower()
    if scelta not in INSTRADAMENTO:
        scelta = "entrambi"                  # al più due specialisti: il tetto è nella tabella

    # 2. ognuno col SUO prompt e i SUOI tool, già costruiti per l'utente.
    #    Nessuno dei due ha un tool che scrive: le azioni restano su /agent,
    #    dove c'è l'approvazione.
    tutti = build_tools_for(user, deps)
    contributi: list[Contributo] = []
    for nome in INSTRADAMENTO[scelta]:
        s = SPECIALISTI[nome]
        run = await run_agent(
            messaggi=[
                {"role": "system", "content": s.system_prompt},
                {"role": "user", "content": domanda},
            ],
            tools=[t for t in tutti if t.name in s.tool_names],
            provider=deps.provider,
            max_steps=settings.agent_max_steps,
        )
        costo += run.cost_eur
        contributi.append(Contributo(
            specialista=s.nome, completo=run.stopped_by == "model",
            stopped_by=run.stopped_by, contenuto=run.reply, tool_calls=run.tool_calls,
        ))

    # 3. la sintesi riceve dati, non prosa incollata: sa chi ha detto cosa e se ha finito
    materiale = json.dumps(
        {"domanda": domanda, "contributi": [c.model_dump() for c in contributi]},
        ensure_ascii=False,
    )
    sintesi = await deps.provider.complete([
        Message(role="system", content=PROMPT_SINTESI),
        Message(role="user", content=materiale),
    ])
    costo += costo_eur(sintesi.cost_eur)
    return SupervisorResult(
        risposta=sintesi.content, instradamento=scelta,
        contributi=contributi, cost_eur=costo,
    )
