import logging

from pydantic import BaseModel, Field

from src.agents.deps import Deps
from src.agents.registry import Tool
from src.auth.deps import UserContext

logger = logging.getLogger(__name__)


class SaldoArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto da interrogare")


class MovimentiArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto")
    n: int = Field(default=5, ge=1, le=50, description="Quanti movimenti restituire")


class RicercaArgs(BaseModel):
    query: str = Field(description="Cosa cercare nelle procedure della banca")


class SegnalazioneArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto segnalato")
    motivo: str = Field(description="Motivo della segnalazione di compliance")


class CartaArgs(BaseModel):
    account_id: str = Field(description="IBAN del conto a cui chiedere le carte")


class BonificoArgs(BaseModel):
    riferimento: str = Field(
        description="Codice riferimento del bonifico, es. TRF-2026-0001"
    )


def build_tools_for(user: UserContext, deps: Deps) -> list[Tool]:
    """Costruisce i tool già legati a questo utente. Fuori da qui l'identità non passa."""

    async def saldo(a: SaldoArgs) -> str:
        # `user` non è un parametro di questa funzione: è nella chiusura, e il modello
        # non ha modo di passarne un altro. È tutta qui la lezione del giorno.
        conto = await deps.accounts.of_user(user.username, a.account_id)
        if conto is None:
            return "Conto non disponibile per questo utente."
        return f"Saldo di {conto.iban}: {conto.saldo:.2f} EUR"

    async def movimenti(a: MovimentiArgs) -> str:
        righe = await deps.movements.recent(user.username, a.account_id, limite=a.n)
        if not righe:
            return "Nessun movimento per questo conto."
        return "\n".join(
            f"{r.date:%d/%m} {r.description} {r.amount:+.2f}" for r in righe
        )

    async def documenti(a: RicercaArgs) -> str:
        # il retrieval di ieri, con l'ACL del ruolo: non è un tool nuovo
        passaggi = await deps.retrieval.search_for_user(
            await deps.embedder.embed_one(a.query), user.username, user.role
        )
        if not passaggi:
            return "Niente nei documenti visibili a questo ruolo."
        return "\n\n".join(f"[{r.document_id}] {r.content[:300]}" for r in passaggi)

    async def segnalazione(a: SegnalazioneArgs) -> str:
        # il solo tool che SCRIVE: al Giorno 8 questa riga passerà da un'approvazione
        conto = await deps.accounts.of_user(user.username, a.account_id)
        if conto is None:
            return "Conto non disponibile per questo utente: segnalazione non aperta."
        alert = await deps.alerts.apri(
            autore=user.username, motivo=a.motivo, account_iban=conto.iban
        )
        return f"Segnalazione {alert.id} aperta."

    async def carte(a: CartaArgs) -> str:
        # Estensione 1: come saldo e movimenti, la JOIN è il controllo d'accesso
        righe = await deps.cards.per_conto(user.username, a.account_id)
        if not righe:
            return "Nessuna carta collegata a questo conto per questo utente."
        return "\n".join(
            f"Carta ...{c.last4} ({c.tipo}): {c.stato}, limite {c.limite:.2f} EUR"
            for c in righe
        )

    async def bonifico(a: BonificoArgs) -> str:
        b = await deps.transfers.per_riferimento(user.username, a.riferimento)
        if b is None:
            return "Bonifico non trovato per questo utente."
        return (
            f"Bonifico {b.riferimento}: {b.stato}, {b.importo:.2f} EUR "
            f"verso {b.destinatario} del {b.data:%d/%m/%Y}"
        )

    return [
        Tool("get_account_balance", "Saldo disponibile di un conto del cliente.",
             SaldoArgs, saldo),
        Tool("list_recent_movements", "Ultimi movimenti di un conto del cliente.",
             MovimentiArgs, movimenti),
        Tool("search_documents", "Cerca nelle procedure e nelle policy della banca.",
             RicercaArgs, documenti),
        Tool("get_card_status", "Stato delle carte collegate a un conto del "
             "cliente: attiva, bloccata o da attivare, con tipo e limite.",
             CartaArgs, carte),
        Tool("get_transfer_status", "Stato di un bonifico gia inviato "
             "(accreditato, in elaborazione o rifiutato) dal suo codice riferimento.",
             BonificoArgs, bonifico),
        Tool("apri_segnalazione_compliance", "Apre una segnalazione di compliance.",
             SegnalazioneArgs, segnalazione),
    ]
