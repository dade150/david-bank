from decimal import Decimal

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import (
    Account,
    Card,
    ChatMessage,
    ChatSession,
    Movement,
    Transfer,
)
from src.types.account import AccountBalance


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(self, user_id: str) -> ChatSession:
        chat = ChatSession(user_id=user_id)
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def find_session(self, session_id: str) -> ChatSession | None:
        stmt = select(ChatSession).where(ChatSession.id == session_id).options(
            selectinload(ChatSession.messages)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        cost_eur: Decimal = Decimal(0),
        model_used: str | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            tokens=tokens,
            cost_eur=cost_eur,
            model_used=model_used,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def list_messages(self, session_id: str) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def movimenti_con_intestatario(self, iban: str) -> list[Row[tuple[Movement, str]]]:
        """
        La JOIN: Restituisce i movimenti affiancati all'ID dell'intestatario del conto.
        """
        stmt = (
            select(Movement, Account.owner_id)
            .join(Account, Account.iban == Movement.account_iban)
            .where(Account.iban == iban)
            .order_by(Movement.date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def totale_speso(self, iban: str) -> tuple[str, int, Decimal] | None:
        """
        L'Aggregazione: Calcola il numero di movimenti e la somma totale spesa.
        """
        stmt = (
            select(
                Account.iban,
                func.count(Movement.id).label("numero_movimenti"),
                func.sum(Movement.amount).label("totale_speso")
            )
            .join(Movement, Movement.account_iban == Account.iban)
            .where(Account.iban == iban)
            .group_by(Account.iban)
        )
        result = await self.session.execute(stmt)
        riga = result.first()
        if riga is None:
            return None
        # la tupla esplicita: l'attributo su Row non è tipizzato, l'unpacking sì
        return str(riga[0]), int(riga[1]), Decimal(riga[2])


class AccountAccess:
    """I conti che QUESTO utente può leggere.

    Il controllo di appartenenza sta dentro la query, insieme al calcolo del
    saldo: non esiste un modo di chiedere un conto senza passare da qui.
    """

    SALDO = (
        select(Account.iban, func.coalesce(func.sum(Movement.amount), 0).label("saldo"))
        .outerjoin(Movement, Movement.account_iban == Account.iban)
        .group_by(Account.iban)
    )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def of_user(self, username: str, account_id: str) -> AccountBalance | None:
        stmt = self.SALDO.where(
            Account.iban == account_id, Account.owner_id == username
        )
        riga = (await self.session.execute(stmt)).first()
        return AccountBalance(iban=riga.iban, saldo=riga.saldo) if riga else None

    async def posseduti(self, username: str) -> list[AccountBalance]:
        stmt = self.SALDO.where(Account.owner_id == username).order_by(Account.iban)
        righe = await self.session.execute(stmt)
        return [AccountBalance(iban=r.iban, saldo=r.saldo) for r in righe]


class MovementAccess:
    """Ultimi movimenti di un conto, sempre che il conto sia dell'utente."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recent(
        self, username: str, account_id: str, limite: int = 5
    ) -> list[Movement]:
        stmt = (
            select(Movement)
            .join(Account, Account.iban == Movement.account_iban)
            .where(Movement.account_iban == account_id, Account.owner_id == username)
            .order_by(Movement.date.desc())
            .limit(limite)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class CardAccess:
    """Le carte collegate a un conto di QUESTO utente.

    La JOIN su accounts è il controllo d'accesso: senza un conto proprio non
    si leggono nemmeno le carte, come per saldo e movimenti.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def per_conto(self, username: str, account_id: str) -> list[Card]:
        stmt = (
            select(Card)
            .join(Account, Account.iban == Card.account_iban)
            .where(Card.account_iban == account_id, Account.owner_id == username)
            .order_by(Card.last4)
        )
        return list((await self.session.execute(stmt)).scalars().all())


class TransferAccess:
    """Un bonifico solo se partito da un conto di QUESTO utente."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def per_riferimento(
        self, username: str, riferimento: str
    ) -> Transfer | None:
        stmt = (
            select(Transfer)
            .join(Account, Account.iban == Transfer.account_iban)
            .where(Transfer.riferimento == riferimento, Account.owner_id == username)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
