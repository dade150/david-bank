import asyncio
import csv
from datetime import datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.db.models import Account, Card, Movement, Transfer

# Dati dell'Estensione 1: due tool del dominio. ID deterministici così il seed
# si riesegue senza creare righe doppie (on_conflict_do_nothing sul PK).
CARTE = [
    {"id": "card-mbianchi", "account_iban": "IT0000000000000000000000001",
     "last4": "4417", "tipo": "debito", "stato": "attiva", "limite": Decimal("2500.00")},
    {"id": "card-ferri", "account_iban": "IT0000000000000000000000002",
     "last4": "8830", "tipo": "credito", "stato": "bloccata", "limite": Decimal("7500.00")},
    {"id": "card-grossi", "account_iban": "IT0000000000000000000000003",
     "last4": "1092", "tipo": "debito", "stato": "da_attivare", "limite": Decimal("1500.00")},
]

BONIFICI = [
    {"riferimento": "TRF-2026-0001", "account_iban": "IT0000000000000000000000001",
     "destinatario": "ERACLE SRL", "importo": Decimal("1250.00"),
     "stato": "accreditato", "data": datetime(2026, 9, 10)},  # noqa: DTZ001
    {"riferimento": "TRF-2026-0002", "account_iban": "IT0000000000000000000000001",
     "destinatario": "MERCURIO LTD", "importo": Decimal("25000.00"),
     "stato": "in_elaborazione", "data": datetime(2026, 9, 25)},  # noqa: DTZ001
    {"riferimento": "TRF-2026-0003", "account_iban": "IT0000000000000000000000002",
     "destinatario": "ZEUS SPA", "importo": Decimal("480.00"),
     "stato": "rifiutato", "data": datetime(2026, 9, 18)},  # noqa: DTZ001
    {"riferimento": "TRF-2026-0004", "account_iban": "IT0000000000000000000000003",
     "destinatario": "ATENA SRL", "importo": Decimal("990.00"),
     "stato": "accreditato", "data": datetime(2026, 9, 5)},  # noqa: DTZ001
]


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
        # 1. Crea i 3 conti (assicurati che gli IBAN combacino con quelli del tuo CSV).
        #    owner_id è lo username in app_users: i tool dell'agente leggono il
        #    conto solo se owner_id coincide con l'utente del token.
        conti = [
            Account(iban="IT0000000000000000000000001", owner_id="mbianchi"),
            Account(iban="IT0000000000000000000000002", owner_id="ferri"),
            Account(iban="IT0000000000000000000000003", owner_id="grossi"),
        ]
        session.add_all(conti)
        await session.flush()  # Invia a Postgres ma non committa ancora

        # 2. Leggi il CSV e inserisci i movimenti
        session.add_all(load_movements())

        # 3. Carte e bonifici dell'Estensione 1: inseriti con ON CONFLICT DO
        #    NOTHING, quindi rieseguire il seed non crea righe doppie.
        session.execute(pg_insert(Card).values(CARTE).on_conflict_do_nothing())
        session.execute(pg_insert(Transfer).values(BONIFICI).on_conflict_do_nothing())

        # 4. Transazione atomica: o salva tutto, o niente
        await session.commit()
        print("✅ Database popolato con successo!")


if __name__ == "__main__":
    asyncio.run(run_seed())
