# src/agents/approval.py — riprendere un run sospeso, dopo che una persona ha deciso
from src.agents.deps import Deps
from src.agents.loop import (
    AgentRun,
    esegui_e_registra,
    richiede_approvazione,
    run_agent,
)
from src.agents.tools import build_tools_for
from src.auth.deps import UserContext
from src.config import settings
from src.db.models import AgentRunState

RIFIUTO = (
    "Il responsabile {da} ha respinto questa azione, che non è stata eseguita. Motivo: {motivo}. "
    "Non ritentarla e non cercare un'altra strada per ottenere lo stesso risultato: riferisci "
    "all'utente che la richiesta è stata respinta, e perché."
)


async def riprendi(
    stato: AgentRunState,
    *,
    approvato: bool,
    da: str,
    motivo: str | None,
    deps: Deps,
) -> AgentRun:
    """Rimette in piedi la conversazione salvata e fa ripartire il ciclo da dove si era fermato.

    I tool si rifanno per CHI HA CHIESTO, mai per chi approva: sono closure sull'utente,
    non dati. E il run riprende con lo stesso id, gli stessi passi e lo stesso costo.
    """
    richiedente = UserContext(username=stato.username, role=stato.role)
    tools = build_tools_for(richiedente, deps)
    per_nome = {t.name: t for t in tools}
    # lo stato è una lista di dizionari, e tale resta: nessun cast, nessun oggetto vivo
    dialogo = [dict(m) for m in stato.messages]
    run = AgentRun(
        run_id=stato.id,
        steps=stato.steps,
        tool_calls=list(stato.tool_calls),
        cost_eur=stato.cost_eur,
    )

    # le chiamate del passo sospeso: ognuna ha diritto alla sua risposta, in ordine
    for dati in stato.pending_calls:
        nome = str(dati.get("tool", ""))
        argomenti = str(dati.get("args", "{}"))
        tool = per_nome.get(nome)
        da_approvare = tool is not None and richiede_approvazione(tool, argomenti)
        if approvato or not da_approvare:
            esito = await esegui_e_registra(per_nome, tool, nome, argomenti, run)
        else:
            esito = RIFIUTO.format(da=da, motivo=motivo)
        dialogo.append(
            {"role": "tool", "content": f"Risultato dello strumento {nome}:\n{esito}"}
        )

    # e il ciclo riparte: stesso dialogo, protocollo già dentro, passi già contati
    return await run_agent(
        messaggi=dialogo,
        tools=tools,
        provider=deps.provider,
        max_steps=settings.agent_max_steps,
        runs=deps.runs,
        user=richiedente,
        run=run,
    )
