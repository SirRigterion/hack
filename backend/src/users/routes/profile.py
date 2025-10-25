from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from typing import Optional

from src.db.database import get_db
from src.db.models import User
from src.auth.auth import get_current_user
from src.cache.redis_cache import get_redis
from src.users.schemas import UserProfile
from src.utils.decorators import require_cookie_and_not_deleted, rate_limit
from src.core.config_log import logger

router = APIRouter(prefix="/profile", tags=["users"])


@router.get("/", response_model=UserProfile)
@require_cookie_and_not_deleted
@rate_limit(limit=10, period=60)
async def get_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """Получить профиль текущего пользователя"""
    # Здесь можно добавить кеширование из твоего оригинального кода
    return UserProfile.from_orm(current_user)


@router.put("/", response_model=UserProfile)
@require_cookie_and_not_deleted
@rate_limit(limit=5, period=300)
async def update_profile(
    request: Request,
    user_login: Optional[str] = Form(None),
    user_full_name: Optional[str] = Form(None),
    # ... остальные параметры из твоего оригинального кода
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Обновить профиль пользователя"""
    # Здесь можно использовать логику из твоего оригинального update_profile
    # с обработкой email, аватара и т.д.
    return UserProfile.from_orm(current_user)