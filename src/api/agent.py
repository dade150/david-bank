from typing import Annotated

from fastapi import APIRouter, Depends

from src.agents.deps import Deps, get_deps
from src.agents.loop import run_agent
from src.agents.tools import build_tools_for
from src.auth.deps import UserContext, get_current_user
from src.config import settings
from src.types.agent import AgentRequest, AgentResponse

router = APIRouter(prefix="/api/ai", tags=["Agent"])

AGENT_SYSTEM = """Sei l'assistente operativo di LipariBank. Rispondi in italiano, in modo breve.

Utente autenticato: {username} (ruolo: {role}).
Conti a cui può accedere: {conti}.
Se l'utente parla del "conto principale" o de "il mio conto", usa il primo della lista.

Hai sei strumenti: saldo, ultimi movimenti, ricerca nei documenti della banca,
stato delle carte collegate a un conto, stato di un bonifico gia inviato,
apertura di una segnalazione di compliance.

Regole:
- Non inventare né IBAN né saldi: ogni dato deve venire da uno strumento.
- Sei tu a chiedere l'accesso, non a deciderlo: per QUALSIASI conto, prima di
  rispondere chiama get_account_balance con l'iban in questione e riferisci
  la risposta del tool, anche se ti sembra ovvio.
- Se l'utente indica un conto senza iban, non chiederglielo: passa al tool ciò
  che ha detto lui (nome, intestatario, descrizione) e riferisci l'esito:
  è il tool a verificare l'accesso, non tu.
- Se il tool rifiuta, dì che non puoi leggere quel conto. Non insistere e non
  indovinare: il rifiuto è la risposta.
- Prima di dire che un'operazione è possibile controlla il saldo con
  get_account_balance e le regole con search_documents.
- Commissioni, limiti e regole di compliance vengono da search_documents,
  non dalla tua memoria.
- Le carte di un conto si verificano con get_card_status: non dedurne lo stato
  dai movimenti o dalle condizioni scritte nei documenti.
- Lo stato di un bonifico viene da get_transfer_status col suo codice
  riferimento (es. TRF-2026-0001): se l'utente non lo cita, chiedilo.
- Apri una segnalazione solo se te lo chiedono esplicitamente.
"""


@router.post("/agent", response_model=AgentResponse)
async def agent(
    payload: AgentRequest,
    user: Annotated[UserContext, Depends(get_current_user)],
    deps: Annotated[Deps, Depends(get_deps)],
) -> AgentResponse:
    conti = await deps.accounts.posseduti(user.username)
    run = await run_agent(
        messaggi=[
            {"role": "system", "content": AGENT_SYSTEM.format(
                username=user.username,
                role=user.role,
                conti=", ".join(c.iban for c in conti) or "nessuno",
            )},
            {"role": "user", "content": payload.message},
        ],
        tools=build_tools_for(user, deps),
        provider=deps.provider,
        max_steps=settings.agent_max_steps,
    )
    return AgentResponse(
        run_id=run.run_id, reply=run.reply, steps=run.steps,
        tool_calls=run.tool_calls, stopped_by=run.stopped_by,
    )
