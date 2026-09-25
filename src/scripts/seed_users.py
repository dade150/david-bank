"""Gli utenti del giorno 6, con la filiale di appartenenza. Script di sviluppo.

    uv run python -m src.scripts.seed_users
"""
import asyncio

from sqlalchemy import select

from src.auth.passwords import hash_password
from src.db.models import AppUser
from src.db.session import AsyncSessionLocal

PASSWORD_DI_SVILUPPO = "bootcamp"

# (username, nome, ruolo, filiale)
# mbianchi e ferri sono operatori di filiali DIVERSE: servono per la prova
# che la stessa domanda dia risposte diverse a seconda dell'appartenenza.
UTENTI = [
    ("mbianchi", "Marco Bianchi", "operator", "MI-01"),
    ("ferri", "Francesca Ferri", "operator", "NA-02"),
    ("grossi", "Giulia Rossi", "compliance_lead", None),   # funzione centrale
    ("lverdi", "Lucia Verdi", "risk_lead", None),          # funzione centrale
]


async def main() -> None:
    print("!! seed di sviluppo: stessa password per tutti, solo sul tuo ambiente")
    creati = 0
    async with AsyncSessionLocal() as session:
        for username, full_name, role, branch_id in UTENTI:
            gia_presente = await session.scalar(
                select(AppUser).where(AppUser.username == username)
            )
            if gia_presente is not None:
                print(f"   {username}: c'era già, lo lascio com'è")
                continue
            session.add(
                AppUser(
                    username=username,
                    full_name=full_name,
                    password_hash=hash_password(PASSWORD_DI_SVILUPPO),
                    role=role,
                    branch_id=branch_id,
                )
            )
            creati += 1
        await session.commit()
    print(f"{creati} utenti creati (password: {PASSWORD_DI_SVILUPPO})")


if __name__ == "__main__":
    asyncio.run(main())
