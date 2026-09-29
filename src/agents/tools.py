import logging
from decimal import Decimal

from pydantic import BaseModel, Field

from src.agents.deps import Deps
from src.agents.registry import Tool
from src.auth.deps import UserContext
from src.config import settings

logger = logging.getLogger(__name__)

NON_DISPONIBILE = "Non risulta nel portafoglio di questo operatore."


class SaldoArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto da interrogare")


class MovimentiArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto")
    n: int = Field(default=5, ge=1, le=50, description="Quanti movimenti restituire")


class RicercaArgs(BaseModel):
    query: str = Field(description="Cosa cercare nelle procedure della banca")


class SegnalazioneArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto segnalato")
    motivo: str = Field(
        min_length=10, max_length=500,
        description="Perché il caso va segnalato, in una o due frasi.",
    )
    importo: Decimal | None = Field(
        default=None, gt=0,
        description="L'importo dell'operazione, se c'è.",
    )


class CartaArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto a cui chiedere le carte")


class BonificoArgs(BaseModel):
    riferimento: str = Field(
        description="Codice riferimento del bonifico, es. TRF-2026-0001"
    )


def build_tools_for(user: UserContext, deps: Deps) -> list[Tool]:
    """Costruisce i tool già legati a questo utente. Fuori da qui l'identità non passa."""

    def rifiuta(tool: str, richiesto: str) -> str:
        # il tentativo si registra: un conto altrui chiesto cinque volte è qualcuno che prova
        logger.warning(
            "tool_accesso_negato",
            extra={"tool": tool, "username": user.username, "requested": richiesto},
        )
        return NON_DISPONIBILE

    async def saldo(a: SaldoArgs) -> str:
        # `user` non è un parametro di questa funzione: è nella chiusura, e il modello
        # non ha modo di passarne un altro. È tutta qui la lezione del giorno.
        conto = await deps.accounts.of_user(user.username, a.account_id)
        if conto is None:
            return rifiuta("get_account_balance", a.account_id)
        return f"Saldo di {conto.iban}: {conto.saldo:.2f} EUR"

    async def movimenti(a: MovimentiArgs) -> str:
        # il pre-check esiste per distinguere il rifiuto dal vuoto: senza, il
        # conto altrui tornerebbe "Nessun movimento", che il modello riferisce come dato
        if await deps.accounts.of_user(user.username, a.account_id) is None:
            return rifiuta("list_recent_movements", a.account_id)
        righe = await deps.movements.recent(user.username, a.account_id, limite=a.n)
        if not righe:
            return "Nessun movimento per questo conto."
        return "\n".join(
            f"{r.date:%d/%m} {r.description} {r.amount:+.2f}" for r in righe
        )

    async def documenti(a: RicercaArgs) -> str:
        # il retrieval del Giorno 6, con l'ACL del ruolo: non è un tool nuovo
        passaggi = await deps.retrieval.search_for_user(
            await deps.embedder.embed_one(a.query), user.username, user.role
        )
        if not passaggi:
            return "Niente nei documenti visibili a questo ruolo."
        return "\n\n".join(f"[{r.document_id}] {r.content[:300]}" for r in passaggi)

    async def segnalazione(a: SegnalazioneArgs) -> str:
        # il solo tool che SCRIVE: il muro vale anche qui, prima di scrivere
        if await deps.accounts.of_user(user.username, a.account_id) is None:
            return rifiuta("apri_segnalazione_compliance", a.account_id)
        try:
            alert, nuova = await deps.alerts.apri(
                autore=user.username, account_iban=a.account_id,
                motivo=a.motivo, importo=a.importo,
            )
        except PermissionError:
            # difesa in profondità: il servizio ha rilevato lo stesso il muro
            return rifiuta("apri_segnalazione_compliance", a.account_id)
        if not nuova:
            return (
                f"La segnalazione {alert.id} su questo conto è già aperta oggi: nessuna "
                "pratica nuova. Riferisci all'utente questo numero e non riaprirla."
            )
        return (
            f"Segnalazione {alert.id} aperta. Riferisci all'utente questo numero di pratica "
            "e che la Compliance la prenderà in carico; non riaprirla."
        )

    async def carte(a: CartaArgs) -> str:
        # Estensione 1: come saldo e movimenti, la JOIN è il controllo d'accesso.
        # Il pre-check serve a non confondere "conto altrui" con "conto senza carte".
        if await deps.accounts.of_user(user.username, a.account_id) is None:
            return rifiuta("get_card_status", a.account_id)
        righe = await deps.cards.per_conto(user.username, a.account_id)
        if not righe:
            return "Nessuna carta collegata a questo conto."
        return "\n".join(
            f"Carta ...{c.last4} ({c.tipo}): {c.stato}, limite {c.limite:.2f} EUR"
            for c in righe
        )

    async def bonifico(a: BonificoArgs) -> str:
        b = await deps.transfers.per_riferimento(user.username, a.riferimento)
        if b is None:
            # stesso identico messaggio per "non esiste" e "è d'un altro": la
            # risposta non deve rivelare l'esistenza di un bonifico altrui
            return "Bonifico non trovato per questo utente."
        return (
            f"Bonifico {b.riferimento}: {b.stato}, {b.importo:.2f} EUR "
            f"verso {b.destinatario} del {b.data:%d/%m/%Y}"
        )

    return [
        Tool("get_account_balance", "Saldo disponibile di un conto del cliente.",
             SaldoArgs, saldo, scrive=False),
        Tool("list_recent_movements", "Ultimi movimenti di un conto del cliente.",
             MovimentiArgs, movimenti, scrive=False),
        Tool("search_documents", "Cerca nelle procedure e nelle policy della banca.",
             RicercaArgs, documenti, scrive=False),
        Tool("get_card_status", "Stato delle carte collegate a un conto del "
             "cliente: attiva, bloccata o da attivare, con tipo e limite.",
             CartaArgs, carte, scrive=False),
        Tool("get_transfer_status", "Stato di un bonifico gia inviato "
             "(accreditato, in elaborazione o rifiutato) dal suo codice riferimento.",
             BonificoArgs, bonifico, scrive=False),
        Tool("apri_segnalazione_compliance", "Apre una segnalazione di compliance.",
             SegnalazioneArgs, segnalazione,
             # Giorno 8: sopra soglia, o senza importo, decide una persona
             serve_approvazione=_sopra_soglia),
    ]


def _sopra_soglia(a: SegnalazioneArgs) -> bool:
    """Un importo che non c'è non è un importo piccolo: nel dubbio si chiede."""
    return a.importo is None or a.importo > settings.soglia_approvazione_eur
