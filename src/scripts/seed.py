import asyncio
import csv
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.db.models import Account, Movement


def load_movements(path: str = "dati_prova.csv") -> list[Movement]:
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            Movement(
                account_iban=row["iban"],
                date=datetime.strptime(row["date"], "%Y-%m-%d"),  # noqa: DTZ007
                description=row["description"],
                amount=Decimal(row["amount"]),  # Fondamentale per non perdere il centesimo
            )
            for row in reader
        ]


async def run_seed():
    engine = create_async_engine(settings.database_url)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        # 1. Crea i 3 conti (assicurati che gli IBAN combacino con quelli del tuo CSV)
        conti = [
            Account(iban="IT0000000000000000000000001", owner_id="cliente_1"),
            Account(iban="IT0000000000000000000000002", owner_id="cliente_2"),
            Account(iban="IT0000000000000000000000003", owner_id="cliente_3"),
        ]
        session.add_all(conti)
        await session.flush()  # Invia a Postgres ma non committa ancora

        # 2. Leggi il CSV e inserisci i movimenti
        session.add_all(load_movements())

        # 3. Transazione atomica: o salva tutto, o niente
        await session.commit()
        print("✅ Database popolato con successo!")


if __name__ == "__main__":
    asyncio.run(run_seed())
