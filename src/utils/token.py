import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.db.models import UserToken


def generate_token() -> str:
    """Генерирует случайный токен (UUID4)."""
    return str(uuid.uuid4())

def hash_token(token: str) -> str:
    """SHA-256 hex хеш."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

async def create_token(
    db: AsyncSession,
    user_id: int,
    token_type: str,
    ttl: int
) -> Tuple[str, str]:
    """
    Создаёт запись UserToken, возвращает (raw_token, token_hash)
    """
    raw = generate_token()
    token_hash = hash_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    token = UserToken(
        user_id=user_id,
        token_hash=token_hash,
        token_type=token_type,
        requested_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        consumed_at=None
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return raw, token_hash

# Найти токен по хэшу и типу (возвращает UserToken или None)
async def get_token_by_hash(
    db: AsyncSession,
    token_hash: str,
    token_type: str
) -> Optional[UserToken]:
    q = await db.execute(select(UserToken).where(UserToken.token_hash == token_hash, UserToken.token_type == token_type))
    return q.scalars().first()

# Отметить токен как использованный (consumed_at = now)
async def consume_user_token(
    db: AsyncSession,
    token: UserToken
) -> None:
    now = datetime.now(timezone.utc)
    await db.execute(
        update(UserToken)
        .where(UserToken.token_id == token.token_id)
        .values(consumed_at=now)
    )
    await db.commit()
