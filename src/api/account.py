from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.services.account_service import AccountService
from src.types.account import MovementResponse, TotalSpentResponse

router = APIRouter(prefix="/api/accounts", tags=["Conti"])

@router.get("/{iban}/movements", response_model=list[MovementResponse])
async def list_movements(
    iban: str,
    session: AsyncSession = Depends(get_db),
) -> list[MovementResponse]:
    service = AccountService(session)
    return await service.get_movimenti(iban)

@router.get("/{iban}/total-spent", response_model=TotalSpentResponse)
async def get_total(
    iban: str,
    session: AsyncSession = Depends(get_db),
) -> TotalSpentResponse:
    service = AccountService(session)
    return await service.get_totale_speso(iban)