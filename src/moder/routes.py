from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Body
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config_app import settings
from src.db.database import get_db
from src.db.models import User, UserStatus
from src.users.schemas import UserRestoreRequest
from src.utils.decorators import require_cookie_and_not_deleted, moder_required, not_banned_required
from src.auth.auth import get_current_user
from src.utils.password import verify_password_with_pepper
from src.core.config_log import logger


router = APIRouter(prefix="/moder", tags=["moder"])

@router.post("/restore/{user_id}")
@require_cookie_and_not_deleted
@moder_required
@not_banned_required
async def restore_user_moder(
    request: Request,
    user_id: int,
    data: UserRestoreRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Восстанавливает удалённого пользователя (is_deleted=False). Нужны данные пользователя.
    """
    result = await db.execute(
        select(User).where(User.user_id == user_id, User.is_deleted == True)
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден или не активен")

    if target_user.user_full_name != data.full_name or target_user.user_login != data.login:
        raise HTTPException(status_code=400, detail="Данные не совпадают")

    plain_for_check = data.password
    if not verify_password_with_pepper(plain_for_check, target_user.user_password_hash, settings.PASSWORD_PEPPER):
        raise HTTPException(status_code=400, detail="Неверный пароль")

    await db.execute(
        update(User).where(User.user_id == target_user.user_id).values(is_deleted=False)
    )
    await db.commit()

    logger.info(f"[MODER] {current_user.user_id} восстановил пользователя {target_user.user_id}")
    return {"detail": "Пользователь восстановлен"}


@router.delete("/delete/{user_id}")
@require_cookie_and_not_deleted
@moder_required
@not_banned_required
async def delete_user_moder(
    request: Request,
    user_id: int,
    data: UserRestoreRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Помечает пользователя как удалённого (is_deleted=True). Нужны данные пользователя.
    """
    result = await db.execute(
        select(User).where(User.user_id == user_id, User.is_deleted == False)
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден или уже удалён")

    if target_user.user_id == 1:
        raise HTTPException(status_code=400, detail="С пользователем с id=1 нельзя выполнять это действие")

    if target_user.user_full_name != data.full_name or target_user.user_login != data.login:
        raise HTTPException(status_code=400, detail="Данные не совпадают")

    plain_for_check = data.password
    if not verify_password_with_pepper(plain_for_check, target_user.user_password_hash, settings.PASSWORD_PEPPER):
        raise HTTPException(status_code=400, detail="Неверный пароль")

    await db.execute(
        update(User).where(User.user_id == target_user.user_id).values(is_deleted=True)
    )
    await db.commit()

    logger.info(f"[MODER] {current_user.user_id} удалил пользователя {target_user.user_id}")
    return {"detail": "Пользователь удалён"}


@router.post("/ban/{user_id}")
@require_cookie_and_not_deleted
@not_banned_required
@moder_required
async def ban_user(
    request: Request,
    user_id: int,
    reason: str = Form(..., description="Причина бана"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Блокирует пользователя. Нужны данные пользователя.
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
    if hasattr(target_user, "ban_reason"):
        updates["ban_reason"] = reason
    if hasattr(target_user, "banned_at"):
        updates["banned_at"] = datetime.now(timezone.utc)

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(**updates))
    await db.commit()

    logger.info(f"[MODER] {current_user.user_id} заблокировал пользователя {target_user.user_id} (reason='{reason}')")
    return {"detail": f"Пользователь {target_user.user_login} заблокирован", "reason": reason}


@router.post("/unban/{user_id}")
@require_cookie_and_not_deleted
@not_banned_required
@moder_required
async def unban_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Разблокирует пользователя. Нужны данные пользователя.
    """
    result = await db.execute(select(User).where(User.user_id == user_id, User.is_deleted == False))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if target_user.user_id == 1:
        raise HTTPException(status_code=400, detail="С пользователем с id=1 нельзя выполнять это действие")

    if target_user.role_id != 1:
        raise HTTPException(status_code=400, detail="Разблокировать можно только пользователей с ролью 1.")
    if target_user.status != UserStatus.BANNED:
        raise HTTPException(status_code=400, detail="Пользователь не заблокирован.")

    await db.execute(update(User).where(User.user_id == target_user.user_id).values(status=UserStatus.ACTIVE))
    await db.commit()

    logger.info(f"[MODER] {current_user.user_id} разблокировал пользователя {target_user.user_id}")
    return {"detail": f"Пользователь {target_user.user_login} разблокирован"}
