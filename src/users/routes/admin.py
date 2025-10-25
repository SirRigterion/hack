from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User
from src.auth.auth import get_current_user
from src.users.services import UserService
from src.utils.decorators import require_cookie_and_not_deleted, admin_required, not_banned_required

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/promote/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def promote_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Повысить пользователя до администратора"""
    try:
        await UserService.change_user_role(db, user_id, 1, current_user.user_id)
        return {"detail": "Пользователь повышен до админа"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/set-role/{user_id}/{role_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def set_user_role(
    request: Request,
    user_id: int,
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Установить роль пользователю"""
    try:
        await UserService.change_user_role(db, user_id, role_id, current_user.user_id)
        return {"detail": f"Роль пользователя установлена в {role_id}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/restore/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def restore_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Восстановить удалённого пользователя"""
    try:
        await UserService.restore_user(db, user_id, current_user.user_id)
        return {"detail": "Пользователь восстановлен"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/delete/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def delete_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить пользователя"""
    try:
        await UserService.delete_user(db, user_id, current_user.user_id)
        return {"detail": "Пользователь удалён"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ban/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def ban_user(
    request: Request,
    user_id: int,
    reason: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Заблокировать пользователя"""
    try:
        await UserService.ban_user(db, user_id, current_user.user_id, reason)
        return {"detail": "Пользователь заблокирован"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/unban/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def unban_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Разблокировать пользователя"""
    try:
        await UserService.unban_user(db, user_id, current_user.user_id)
        return {"detail": "Пользователь разблокирован"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))