import json
import logging
import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import ValidationError

from src.agents.registry import Tool
from src.auth.deps import UserContext
from src.db.runs import RunRepository
from src.llm.llm_types import Message
from src.llm.opencode_provider import OpencodeProvider

logger = logging.getLogger(__name__)

BUDGET_PER_RUN = Decimal("0.05")  # euro

_TESTO_PROTOCOLLO = """
REGOLE DI RISPOSTA (le uniche):
- Quando ti serve uno strumento rispondi SOLO con il JSON:
  {"tool": "<nome>", "args": {<argomenti>}}
  Nessun testo prima o dopo, nessun markdown, niente codice frazionato.
- Quando hai la risposta finale rispondi in italiano normale, SENZA alcun JSON.

Strumenti disponibili (JSON schema):
"""

SENZA_APPROVAZIONE = (
    "Questa azione richiede l'approvazione di un responsabile, e da qui non si può chiedere: "
    "non è stata eseguita. Non ritentarla: riferisci all'utente che va richiesta dal flusso "
    "con approvazione."
)


@dataclass
class AgentRun:
    """Esito di un run: quello che l'endpoint restituisce e quello che si traccia."""

    run_id: str
    reply: str = ""
    steps: int = 0
    tool_calls: list[str] = field(default_factory=list)
    stopped_by: str = "max_steps"   # "model" | "max_steps" | "budget" | "awaiting_approval"
    cost_eur: Decimal = Decimal(0)


async def run_agent(
    messaggi: list[dict],
    tools: Sequence[Tool],
    provider: OpencodeProvider,
    max_steps: int = 6,
    *,
    runs: RunRepository | None = None,
    user: UserContext | None = None,
    run: AgentRun | None = None,
) -> AgentRun:
    """Il loop: chiedi, esegui i tool, rimetti tutto nella conversazione, ripeti.

    Tre regole che se le sbagli si vedono subito:
    - il messaggio dell'assistente entra nella conversazione PRIMA dei risultati,
      altrimenti il modello riceve osservazioni che non ha richiesto;
    - uscire per esaurire i passi non è un successo: `stopped_by` lo dice;
    - un tool che scrive si ferma prima di partire, se c'è qualcuno che deve
      dare il permesso (`runs` e `user`). Senza di loro non è un via libera.

    `run` è il run da riprendere: a quel punto `messaggi` è già la conversazione
    completa, protocollo compreso, e qui non si aggiunge niente.
    """
    if run is None:
        run = AgentRun(run_id=str(uuid.uuid4()))
        schemi = "\n".join(
            json.dumps(t.to_openai_schema(), ensure_ascii=False) for t in tools
        )
        dialogo = [*messaggi, {"role": "system", "content": _TESTO_PROTOCOLLO + schemi}]
    else:
        dialogo = list(messaggi)

    return await _ciclo(
        dialogo, tools, provider, max_steps, run, runs=runs, user=user
    )


async def _ciclo(
    dialogo: list[dict],
    tools: Sequence[Tool],
    provider: OpencodeProvider,
    max_steps: int,
    run: AgentRun,
    *,
    runs: RunRepository | None = None,
    user: UserContext | None = None,
) -> AgentRun:
    """Il corpo del loop, sul dialogo già costruito. Lo usa anche la ripresa."""
    per_nome = {t.name: t for t in tools}

    # il tetto conta anche i passi fatti prima: alla ripresa si riparte da lì
    for passo in range(run.steps + 1, max_steps + 1):
        run.steps = passo
        testo, _tokens, costo = await _chiedi(provider, dialogo)
        run.cost_eur += costo
        chiamata = _parsa_strumento(testo)

        # PRIMA dei risultati: il modello deve vedere la sua stessa richiesta.
        dialogo.append({"role": "assistant", "content": testo})

        if chiamata is None:
            run.reply = testo
            run.stopped_by = "model"
            return run

        if run.cost_eur > BUDGET_PER_RUN:
            # uscita per budget, prima di altri tool: si ferma qui, non dopo
            run.stopped_by = "budget"
            run.reply = (
                "Ho interrotto l'elaborazione perché la richiesta ha superato il "
                "budget previsto. Prova a formularla in modo più circoscritto."
            )
            return run

        nome, argomenti = chiamata
        tool = per_nome.get(nome)

        if tool is not None and richiede_approvazione(tool, argomenti):
            if runs is not None and user is not None:
                # uscita 4: QUESTO passo non parte affatto. Alla ripresa parte il tool,
                # con gli stessi argomenti, e il ciclo riprende dal passo dopo.
                descrizione = descrivi_attesa(tool, argomenti, user, run.run_id)
                await runs.sospendi(
                    run_id=run.run_id, username=user.username, role=user.role,
                    messages=[dict(m) for m in dialogo],
                    pending_calls=[{"tool": nome, "args": argomenti}],
                    description=descrizione,
                    steps=run.steps, cost_eur=run.cost_eur,
                    tool_calls=list(run.tool_calls),
                )
                run.stopped_by = "awaiting_approval"
                run.reply = descrizione
                return run
            # nessuno a cui chiedere: non è un via libera, è un muro
            logger.warning(
                "tool_senza_approvazione",
                extra={"run_id": run.run_id, "tool": nome},
            )
            esito = SENZA_APPROVAZIONE
        else:
            esito = await esegui_e_registra(per_nome, tool, nome, argomenti, run)

        dialogo.append(
            {"role": "tool", "content": f"Risultato dello strumento {nome}:\n{esito}"}
        )

    if not run.reply:
        run.stopped_by = "max_steps"
        run.reply = (
            "Non ho completato la richiesta entro i passi previsti: la risposta non c'è. "
            "Riformula la domanda in modo più specifico, o dividila in domande più semplici."
        )
    return run


def richiede_approvazione(tool: Tool | None, argomenti: str) -> bool:
    """Serve una persona per questa chiamata? Nel dubbio sì.

    Gli argomenti qui vengono validati: se sono rotti la chiamata non partirà lo
    stesso (il loop gli restituisce l'errore), quindi non c'è nulla da approvare.
    """
    if tool is None or not tool.scrive:
        return False                      # un nome inventato o un tool in lettura
    try:
        args = tool.args_model.model_validate_json(argomenti)
    except ValidationError:
        return False                      # non partirà: _esegui rimanda l'errore
    return tool.serve_approvazione is None or tool.serve_approvazione(args)


def descrivi_attesa(
    tool: Tool, argomenti: str, user: UserContext, run_id: str
) -> str:
    """Cosa sta per succedere, in una forma che una persona può approvare o respingere."""
    args = tool.args_model.model_validate_json(argomenti)
    campi = ", ".join(
        f"{k}={v}" for k, v in args.model_dump(mode="json").items() if v is not None
    )
    return (
        f"Serve l'approvazione di un responsabile, richiesta da {user.username}, per:\n"
        f"- {tool.name}: {campi}\n"
        f"Pratica in attesa: {run_id}. Nulla è stato ancora eseguito."
    )


async def esegui_e_registra(
    per_nome: dict[str, Tool],
    tool: Tool | None,
    nome: str,
    argomenti: str,
    run: AgentRun,
) -> str:
    """Esegue un tool e ne lascia la riga di traccia. La usa anche la ripresa."""
    run.tool_calls.append(nome)
    inizio = time.perf_counter()
    esito = await _esegui(per_nome, tool, nome, argomenti, run)
    logger.info(
        "agent_step",
        extra={
            "run_id": run.run_id,
            "step": run.steps,
            "tool": nome,
            # gli argomenti di un tool che scrive non vanno nel log:
            # stanno nella sua tabella
            "tool_args": "<omessi>" if tool is None or tool.scrive else argomenti[:200],
            "result_preview": esito[:200],
            "result_len": len(esito),
            "duration_ms": int((time.perf_counter() - inizio) * 1000),
        },
    )
    return esito


async def _chiedi(
    provider: OpencodeProvider, dialogo: list[dict]
) -> tuple[str, int, Decimal]:
    """Una chiamata al modello: il dialogo diventa testo, come fa già chat/advice.

    Il costo arriva già calcolato dal provider: qui si accumula, non si butta via.
    """
    risposta = await provider.complete(
        [Message(role=m["role"], content=str(m["content"])) for m in dialogo],
    )
    return risposta.content, risposta.tokens_used, costo_eur(risposta.cost_eur)


def costo_eur(valore: float) -> Decimal:
    """Dal float del provider al Decimal del conto, in euro.

    Via str, altrimenti il binario entra nel euro e il budget non torna mai.
    Lo usa anche il supervisor.
    """
    return Decimal(str(valore))


def _parsa_strumento(testo: str) -> tuple[str, str] | None:
    """(nome, args-json) se è una richiesta di tool, altrimenti None: è la risposta.

    Tollera JSON puro, JSON dentro ``` e prosa attorno. Se il modello sbaglia
    a scrivere il JSON, quella risposta vale come risposta finale: meglio una
    risposta mediocre che un loop che si lamenta.
    """
    corpo = testo.strip()
    if corpo.startswith("```"):
        corpo = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", corpo).strip()

    inizio = corpo.find("{")
    while inizio != -1:
        chiuso = _oggetto_bilanciato(corpo, inizio)
        if chiuso is not None:
            try:
                d = json.loads(corpo[inizio : chiuso + 1])
            except json.JSONDecodeError:
                d = None
            if isinstance(d, dict):
                nome = d.get("tool") or d.get("name")
                if isinstance(nome, str) and nome:
                    args = d.get("args") or d.get("arguments") or {}
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    return nome, args
        inizio = corpo.find("{", inizio + 1)
    return None


def _oggetto_bilanciato(testo: str, inizio: int) -> int | None:
    """Indice della graffa che chiude l'oggetto aperto in `inizio`."""
    profondita = 0
    for i, c in enumerate(testo[inizio:], start=inizio):
        if c == "{":
            profondita += 1
        elif c == "}":
            profondita -= 1
            if profondita == 0:
                return i
    return None


async def _esegui(
    per_nome: dict[str, Tool], tool: Tool | None, nome: str, argomenti: str, run: AgentRun
) -> str:
    """Un tool che esplode non deve fare esplodere la richiesta: l'errore è una risposta."""
    if tool is None:
        # il modello ha inventato un nome: glielo diciamo, non solleviamo
        logger.warning("tool_inesistente", extra={"tool": nome[:80]})
        elenco = f"Tool disponibili: {', '.join(sorted(per_nome))}." if per_nome else ""
        return f"ERRORE: il tool '{nome}' non esiste. {elenco}".strip()
    try:
        return await tool.run(tool.args_model.model_validate_json(argomenti))
    except Exception as exc:
        # un tool che fallisce (database lento, vincolo violato) è un'osservazione, non un 500
        logger.exception("run=%s tool=%s fallito", run.run_id, nome)
        return (
            f"ERRORE: il tool '{nome}' non ha potuto completare l'operazione. "
            "Non riprovare la stessa chiamata: riferisci all'utente che il dato "
            f"ora non è disponibile. ({exc.__class__.__name__})"
        )
