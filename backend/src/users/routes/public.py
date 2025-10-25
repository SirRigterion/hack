from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User
from src.auth.auth import get_current_user
from src.users.schemas import UserProfile
from src.utils.decorators import require_cookie_and_not_deleted, not_banned_required, rate_limit

router = APIRouter(prefix="", tags=["users"])


@router.get("/search", response_model=List[UserProfile])
@require_cookie_and_not_deleted
@not_banned_required
@rate_limit(limit=20, period=60)
async def search_users(
        request: Request,
        user_login: Optional[str] = None,
        user_full_name: Optional[str] = None,
        limit: int = Query(10, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Поиск пользователей"""
    # Здесь можно добавить логику поиска из твоего оригинального кода
    return []


@router.get("/{user_id}", response_model=UserProfile)
@require_cookie_and_not_deleted
@not_banned_required
@rate_limit(limit=30, period=60)
async def get_user_by_id(
        request: Request,
        user_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """Получить пользователя по ID"""
    # Здесь можно добавить логику из твоего оригинального get_user_profile
    result = await db.execute(
        select(User).where(User.user_id == user_id, User.is_deleted == False)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return UserProfile.from_orm(user)