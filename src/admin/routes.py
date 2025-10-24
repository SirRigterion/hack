from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from src.db.models import User, UserStatus
from src.db.database import get_db
from src.utils.decorators import require_cookie_and_not_deleted, admin_required, not_banned_required
from src.auth.auth import get_current_user
from src.core.config_log import logger


router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/promote/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def promote(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Повышает указанного пользователя до роли администратора (role_id=1).
    """
    result = await db.execute(select(User).where(User.user_id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if target_user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Нельзя изменять собственные права")
    if target_user.user_id == 1:
        raise HTTPException(status_code=400, detail="С пользователем с id=1 нельзя выполнять это действие")

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(role_id=1))
    await db.commit()

    logger.info(f"[ADMIN] {current_user.user_id} повысил пользователя {target_user.user_id} до админа")
    return {"detail": "Пользователь повышен до админа"}


@router.post("/set-role/{user_id}/{role_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def set_role(
    request: Request,
    user_id: int,
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Устанавливает произвольную роль пользователю.
    """
    result = await db.execute(select(User).where(User.user_id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if target_user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Нельзя изменять собственные права")
    if target_user.user_id == 1:
        raise HTTPException(status_code=400, detail="С пользователем с id=1 нельзя выполнять это действие")

    if role_id not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Неверная роль")

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(role_id=role_id))
    await db.commit()

    logger.info(f"[ADMIN] {current_user.user_id} установил роль {role_id} пользователю {target_user.user_id}")
    return {"detail": f"Роль пользователя {target_user.user_id} установлена в {role_id}"}


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
    """
    Восстанавливает удалённого пользователя (is_deleted=False).
    """
    result = await db.execute(select(User).where(User.user_id == user_id, User.is_deleted == True))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден или не удалён")

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(is_deleted=False))
    await db.commit()

    logger.info(f"[ADMIN] {current_user.user_id} восстановил пользователя {target_user.user_id}")
    return {"detail": "Пользователь восстановлен"}


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
    """
    Помечает пользователя как удалённого (is_deleted=True).
    """
    result = await db.execute(select(User).where(User.user_id == user_id, User.is_deleted == False))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if target_user.user_id == 1:
        raise HTTPException(status_code=400, detail="С пользователем с id=1 нельзя выполнять это действие")
    if target_user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя.")

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(is_deleted=True))
    await db.commit()

    logger.info(f"[ADMIN] {current_user.user_id} удалил пользователя {target_user.user_id}")
    return {"detail": "Пользователь удалён"}


@router.post("/ban/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def admin_ban_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Блокирует пользователя.
    """
    result = await db.execute(select(User).where(User.user_id == user_id, User.is_deleted == False))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if target_user.user_id == 1:
        raise HTTPException(status_code=400, detail="С пользователем с id=1 нельзя выполнять это действие")
    if target_user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Нельзя банить самого себя.")

    updates = {"status": UserStatus.BANNED}
    if hasattr(target_user, "banned_at"):
        updates["banned_at"] = datetime.now(timezone.utc)

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(**updates))
    await db.commit()

    logger.info(f"[ADMIN] {current_user.user_id} заблокировал пользователя {target_user.user_id}")
    return {"detail": f"Пользователь {target_user.user_login} заблокирован"}


@router.post("/unban/{user_id}")
@require_cookie_and_not_deleted
@admin_required
@not_banned_required
async def admin_unban_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Разблокирует пользователя.
    """
    result = await db.execute(select(User).where(User.user_id == user_id, User.is_deleted == False))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if target_user.user_id == 1:
        raise HTTPException(status_code=400, detail="С пользователем с id=1 нельзя выполнять это действие")

    if target_user.status != UserStatus.BANNED:
        raise HTTPException(status_code=400, detail="Пользователь не заблокирован.")

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(status=UserStatus.ACTIVE))
    await db.commit()

    logger.info(f"[ADMIN] {current_user.user_id} разблокировал пользователя {target_user.user_id}")
    return {"detail": f"Пользователь {target_user.user_login} разблокирован"}
