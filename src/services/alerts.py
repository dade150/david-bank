"""L'unico punto del progetto che apre una segnalazione di compliance.

Due garanzie che stanno qui e non nel tool che la invoca:
- il controllo d'accesso è ripetuto internamente, con una query propria:
  un qualsiasi altro chiamante (script, tool futuro, endpoint) non può
  scrivere su un conto che non è del portafoglio di chi scrive;
- l'idempotenza è sul vincolo di unicità della chiave: una pratica per
  conto, operatore e giorno. La seconda chiamata dello stesso giorno
  restituisce la riga già aperta invece di crearne un'altra.
"""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Account, ComplianceAlert

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def apri(
        self, *, autore: str, account_iban: str, motivo: str, importo: Decimal | None = None
    ) -> tuple[ComplianceAlert, bool]:
        """Apre la segnalazione, o restituisce quella già aperta.

        Il bool dice se è una riga nuova: chi chiama deve saperlo, perché
        "aperta" e "era già aperta" sono due risposte diverse per l'utente.
        """
        # secondo controllo, indipendente da chi chiama e dal tool che chiama
        proprietario = await self.session.scalar(
            select(Account.owner_id).where(Account.iban == account_iban)
        )
        if proprietario is None or proprietario != autore:
            logger.warning(
                "alert_accesso_negato",
                extra={"username": autore, "requested": account_iban},
            )
            raise PermissionError(
                f"{autore} non ha in portafoglio il conto {account_iban}"
            )

        # una pratica per conto, per operatore, al giorno
        chiave = self.chiave(account_iban, autore, datetime.now(UTC).date())
        esistente = await self._per_chiave(chiave)
        if esistente is not None:
            return esistente, False

        alert = ComplianceAlert(
            account_iban=account_iban,
            opened_by=autore,
            reason=motivo,
            amount=importo,
            idempotency_key=chiave,
        )
        try:
            async with self.session.begin_nested():  # due chiamate insieme: decide il vincolo
                self.session.add(alert)
                await self.session.flush()
        except IntegrityError:
            # un'altra richiesta ha inserito la stessa riga fra le due query
            vincitrice = await self._per_chiave(chiave)
            if vincitrice is None:
                raise
            return vincitrice, False
        await self.session.commit()
        return alert, True

    @staticmethod
    def chiave(account_iban: str, autore: str, giorno: date) -> str:
        return f"{account_iban}:{autore}:{giorno.isoformat()}"

    async def _per_chiave(self, chiave: str) -> ComplianceAlert | None:
        return await self.session.scalar(
            select(ComplianceAlert).where(ComplianceAlert.idempotency_key == chiave)
        )
