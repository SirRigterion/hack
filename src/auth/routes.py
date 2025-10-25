from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User, UserStatus
from src.auth.auth import create_access_token, get_current_user, set_auth_cookie
from src.auth.schemas import UserCreate, UserLogin
from src.users.schemas import UserProfile

from src.core.config_log import logger
from src.core.config_app import settings
from src.utils.password import hash_password_with_pepper, verify_password_with_pepper
from src.utils.decorators import rate_limit, require_cookie_and_not_deleted
from src.utils.email import send_verification_email
from src.utils.token import create_token, get_token_by_hash, consume_user_token, hash_token
from src.cache.redis_cache import cache_user_profile, incr, delete

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserProfile, status_code=201)
@rate_limit(limit=3, period=300)
async def register(
    request: Request,
    user: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Проверка уникальности email / login
    result = await db.execute(
        select(User).where(
            (User.user_email == user.user_email) | (User.user_login == user.user_login)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Электронная почта или логин уже зарегистрированы")

    try:
        # Хэш пароля с использованием правильного метода
        pepper = settings.PASSWORD_PEPPER or ""
        hashed_password = hash_password_with_pepper(user.user_password, pepper)

        # Создаём пользователя
        new_user = User(
            user_login=user.user_login,
            user_full_name=user.user_full_name,
            user_email=user.user_email,
            user_password_hash=hashed_password,
            user_salt="",
            role_id=3,
            status=UserStatus.REGISTERED,
            is_deleted=False,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # Создаём верификационный токен в user_tokens
        raw_token, _ = await create_token(
            db=db,
            user_id=new_user.user_id,
            token_type="email_verification",
            ttl=int(settings.TOKEN_TTL_SECONDS),
        )

        # Письмо с подтверждением
        try:
            await send_verification_email(new_user.user_email, new_user.user_full_name, raw_token)
        except Exception as e:
            logger.error(f"Ошибка отправки письма на {new_user.user_email}: {e}")

        # Попытка кэширования профиля в Redis (без перезаписи, если уже есть)
        try:
            await cache_user_profile(None, new_user, force=False)
        except Exception as e:
            logger.debug(f"register: исключение при записи в Redis для user_id={new_user.user_id}: {e}")

        # JWT + cookie
        token = create_access_token(subject=str(new_user.user_id), roles=[new_user.role_id])
        set_auth_cookie(response, token)

        logger.info(f"Пользователь {user.user_login} успешно зарегистрирован")
        return UserProfile.from_orm(new_user)

    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка регистрации пользователя: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/resend-verification")
@require_cookie_and_not_deleted
async def resend_verification(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.status == UserStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Аккаунт уже подтверждён")

    max_retries = settings.TOKEN_RESEND_MAX
    window = settings.TOKEN_RESEND_WINDOW_SECONDS
    key = f"verif:resend:{current_user.user_id}"

    # Попытка инкремента в Redis
    try:
        new_val = await incr(key, amount=1, ttl=window)
    except Exception as e:
        logger.warning(f"resend_verification: Redis error during incr: {e}")
        new_val = None

    if new_val is None:
        logger.debug(f"resend_verification: Redis недоступен, пропускаем rate-limit для user_id={current_user.user_id}")
    else:
        if int(new_val) > max_retries:
            raise HTTPException(status_code=429, detail="Слишком много запросов, попробуйте позже.")

    # Создаём токен и отправляем письмо
    try:
        raw_token, _ = await create_token(
            db=db,
            user_id=current_user.user_id,
            token_type="email_verification",
            ttl=int(settings.TOKEN_TTL_SECONDS),
        )
    except Exception as e:
        logger.error(f"Ошибка создания токена подтверждения user_id={current_user.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Не удалось создать токен подтверждения")

    try:
        await send_verification_email(current_user.user_email, current_user.user_full_name, raw_token)
    except Exception as e:
        logger.error(f"Не удалось отправить письмо подтверждения user_id={current_user.user_id}: {e}")

    return {"detail": "Письмо с подтверждением отправлено"}


@router.get("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    token_hash_val = hash_token(token)

    # Ищем токен
    db_token = await get_token_by_hash(db, token_hash_val, "email_verification")
    if not db_token:
        raise HTTPException(status_code=400, detail="Неверный или устаревший токен подтверждения")

    now = datetime.now(timezone.utc)
    if db_token.expires_at and db_token.expires_at < now:
        raise HTTPException(status_code=400, detail="Срок действия токена истёк")
    if db_token.consumed_at is not None:
        raise HTTPException(status_code=400, detail="Токен уже был использован")

    # Активируем пользователя
    result = await db.execute(select(User).where(User.user_id == db_token.user_id))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=400, detail="Пользователь не найден для данного токена")

    db_user.status = UserStatus.ACTIVE
    await db.commit()
    await db.refresh(db_user)

    # Помечаем токен использованным
    await consume_user_token(db, db_token)

    # Обновляем кеш профиля — принудительно, т.к. статус изменился
    try:
        await cache_user_profile(None, db_user, force=True)
    except Exception as e:
        logger.debug(f"verify_email: исключение при записи в Redis для user_id={db_user.user_id}: {e}")

    return {"message": "Email успешно подтвержден"}


@router.post("/login", response_model=UserProfile, status_code=200)
@rate_limit(limit=5, period=60)
async def login(
    request: Request,
    user: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Аутентифицирует пользователя."""
    q = select(User).where(
        or_(
            User.user_login == user.user_indificator,
            User.user_email == user.user_indificator
        )
    )
    result = await db.execute(q)
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    pepper = settings.PASSWORD_PEPPER or ""
    if not verify_password_with_pepper(user.user_password, db_user.user_password_hash, pepper):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    if db_user.status == UserStatus.REGISTERED:
        raise HTTPException(status_code=403, detail="Подтвердите email перед входом")
    elif db_user.status == UserStatus.BANNED:
        raise HTTPException(status_code=403, detail="Ваш аккаунт заблокирован")
    elif db_user.is_deleted:
        raise HTTPException(status_code=403, detail="Аккаунт удалён")

    try:
        token = create_access_token(subject=str(db_user.user_id), roles=[db_user.role_id])
        set_auth_cookie(response, token)

        try:
            await cache_user_profile(None, db_user, force=False)
        except Exception as e:
            logger.debug(f"login: исключение при записи в Redis для user_id={db_user.user_id}: {e}")

        logger.info(f"Пользователь {db_user.user_login} успешно вошел в систему")
        return UserProfile.from_orm(db_user)

    except Exception as e:
        logger.error(f"Ошибка входа пользователя: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/logout", response_model=dict, status_code=200)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """Удаляет токен из cookie и очищает профиль в Redis."""
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=True,
    )

    try:
        ok = await delete(f"user:profile:{current_user.user_id}")
        if not ok:
            logger.debug(f"logout: не удалось удалить кэш для user_id={current_user.user_id} или Redis недоступен")
    except Exception as e:
        logger.debug(f"logout: исключение при удалении кэша для user_id={current_user.user_id}: {e}")

    logger.info(f"Пользователь {current_user.user_id} успешно вышел из системы")
    return {"message": "Выход выполнен успешно"}
