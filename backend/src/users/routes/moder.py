from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User
from src.auth.auth import get_current_user
from src.users.services import UserService
from src.utils.decorators import require_cookie_and_not_deleted, moder_required, not_banned_required

router = APIRouter(prefix="/moder", tags=["moder"])


@router.post("/ban/{user_id}")
@require_cookie_and_not_deleted
@moder_required
@not_banned_required
async def ban_user(
        request: Request,
        user_id: int,
        reason: str = None,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Заблокировать пользователя (только обычных пользователей)"""
    try:
        # Модераторы могут банить только пользователей с role_id=3
        target_user = await UserService.get_user_by_id(db, user_id)
        if target_user.role_id != 3:
            raise ValueError("Модераторы могут блокировать только обычных пользователей")

        await UserService.ban_user(db, user_id, current_user.user_id, reason)
        return {"detail": "Пользователь заблокирован"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/unban/{user_id}")
@require_cookie_and_not_deleted
@moder_required
@not_banned_required
async def unban_user(
        request: Request,
        user_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Разблокировать пользователя (только обычных пользователей)"""
    try:
        # Модераторы могут разбанивать только пользователей с role_id=3
        target_user = await UserService.get_user_by_id(db, user_id)
        if target_user.role_id != 3:
            raise ValueError("Модераторы могут разблокировать только обычных пользователей")

        await UserService.unban_user(db, user_id, current_user.user_id)
        return {"detail": "Пользователь разблокирован"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))