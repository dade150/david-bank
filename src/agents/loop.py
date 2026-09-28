import json
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.agents.registry import Tool
from src.llm.opencode_provider import OpencodeProvider
from src.llm.types import Message

logger = logging.getLogger(__name__)

_TESTO_PROTOCOLLO = """
REGOLE DI RISPOSTA (le uniche):
- Quando ti serve uno strumento rispondi SOLO con il JSON:
  {"tool": "<nome>", "args": {<argomenti>}}
  Nessun testo prima o dopo, nessun markdown, niente codice frazionato.
- Quando hai la risposta finale rispondi in italiano normale, SENZA alcun JSON.

Strumenti disponibili (JSON schema):
"""


@dataclass
class AgentRun:
    """Esito di un run: quello che l'endpoint restituisce e quello che si traccia."""

    run_id: str
    reply: str = ""
    steps: int = 0
    tool_calls: list[str] = field(default_factory=list)
    stopped_by: str = "max_steps"


async def run_agent(
    messaggi: list[dict],
    tools: Sequence[Tool],
    provider: OpencodeProvider,
    max_steps: int = 6,
) -> AgentRun:
    """Il loop: chiedi, esegui i tool, rimetti tutto nella conversazione, ripeti.

    Due regole che se le sbagli si vedono subito:
    - il messaggio dell'assistente entra nella conversazione PRIMA dei risultati,
      altrimenti il modello riceve osservazioni che non ha richiesto;
    - uscire per esaurire i passi non è un successo: `stopped_by` lo dice.

    Il modello non ha accesso a niente: ogni cosa che vede gliel'abbiamo passata
    noi. I tool non esistono per lui, esistono solo come schema JSON nel prompt.
    """
    run = AgentRun(run_id=str(uuid.uuid4()))
    per_nome = {t.name: t for t in tools}
    schemi = "\n".join(
        json.dumps(t.to_openai_schema(), ensure_ascii=False) for t in tools
    )
    dialogo = [*messaggi, {"role": "system", "content": _TESTO_PROTOCOLLO + schemi}]

    for passo in range(1, max_steps + 1):
        testo, tokens = await _chiedi(provider, dialogo)
        run.steps = passo
        chiamata = _parsa_strumento(testo)

        # PRIMA dei risultati: il modello deve vedere la sua stessa richiesta.
        dialogo.append({"role": "assistant", "content": testo})

        if chiamata is None:
            run.reply = testo
            run.stopped_by = "model"
            return run

        nome, argomenti = chiamata
        run.tool_calls.append(nome)
        esito = await _esegui(per_nome.get(nome), nome, argomenti, run)
        dialogo.append(
            {"role": "tool", "content": f"Risultato dello strumento {nome}:\n{esito}"}
        )

        logger.info(
            "run=%s passo=%s/%s tool=%s tokens=%s",
            run.run_id, passo, max_steps, nome, tokens,
        )

    if not run.reply:
        run.reply = "Limite di passi raggiunto: non sono arrivato a una risposta."
    return run


async def _chiedi(provider: OpencodeProvider, dialogo: list[dict]) -> tuple[str, int]:
    """Una chiamata al modello: il dialogo diventa testo, come fa già chat/advice."""
    risposta = await provider.complete(
        [Message(role=m["role"], content=str(m["content"])) for m in dialogo],
    )
    return risposta.content, risposta.tokens_used


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
    tool: Tool | None, nome: str, argomenti: str, run: AgentRun
) -> str:
    """Un tool che esplode non deve fare esplodere la richiesta: l'errore è una risposta."""
    if tool is None:
        return f"Tool sconosciuto: {nome}."
    try:
        return await tool.run(tool.args_model.model_validate_json(argomenti))
    except Exception as exc:
        logger.exception("run=%s tool=%s fallito", run.run_id, nome)
        return f"Errore nel tool {nome}: {exc}"
