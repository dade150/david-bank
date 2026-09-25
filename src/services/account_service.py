from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repos import AccountRepository
from src.exception import AppError
from src.types.account import MovementResponse, TotalSpentResponse


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AccountRepository(session)

    async def get_movimenti(self, iban: str) -> list[MovementResponse]:
        righe = await self.repo.movimenti_con_intestatario(iban)

        return [
            MovementResponse(
                id=movimento.id,
                date=movimento.date,
                description=movimento.description,
                amount=movimento.amount,
                owner_id=owner_id
            )
            for movimento, owner_id in righe
        ]

    async def get_totale_speso(self, iban: str) -> TotalSpentResponse:
        risultato = await self.repo.totale_speso(iban)

        if not risultato:
            raise AppError(404, "ACCOUNT_NOT_FOUND", f"Conto {iban} non trovato o senza movimenti")

        return TotalSpentResponse(
            iban=risultato.iban,
            numero_movimenti=risultato.numero_movimenti,
            totale_speso=risultato.totale_speso
        )