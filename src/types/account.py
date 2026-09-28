from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class MovementResponse(BaseModel):
    id: int
    date: datetime
    description: str
    amount: Decimal
    owner_id: str

class TotalSpentResponse(BaseModel):
    iban: str
    numero_movimenti: int
    totale_speso: Decimal

class AccountBalance(BaseModel):
    """Conto visto dall'agente: l'iban e il saldo calcolato dai movimenti."""

    iban: str
    saldo: Decimal