import json
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File, status, Query
from pydantic import EmailStr, ValidationError as PydanticValidationError
import redis.asyncio as redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.redis_cache import cache_user_profile, get_redis
from src.images.utils import save_uploaded_file
from src.auth.auth import get_current_user
from src.db.database import get_db
from src.db.models import User, UserStatus, UserToken
from src.users.schemas import UserProfile
from src.core.config_app import settings
from src.core.config_log import logger
from src.utils.decorators import require_cookie_and_not_deleted, not_banned_required, rate_limit
from src.core.exceptions import (
    ValidationError, AuthorizationError, 
    NotFoundError, ConflictError, InternalServerError
)
from src.utils.email import send_email, send_reset_password, send_verification_email, send_deletion_email
from src.utils.token import create_token, get_token_by_hash, consume_user_token, hash_token
from src.utils.password import hash_password_with_pepper


router = APIRouter(prefix="/user", tags=["user"])

async def _decode_redis_bytes(value: Optional[bytes]) -> Optional[str]:
    """Декодирует значение из Redis в str (без возбуждения исключений)."""
    if value is None:
        return None
    try:
        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8")
        return str(value)
    except (UnicodeDecodeError, AttributeError) as e:
        logger.warning(f"_decode_redis_bytes: ошибка декодирования: {e}")
        return None
    except Exception as e:
        logger.error(f"_decode_redis_bytes: неожиданная ошибка: {e}")
        return None


async def _safe_redis_get(redis_client: Optional[redis.Redis], key: str) -> Optional[str]:
    """Безопасное получение значения из Redis с обработкой ошибок."""
    if not redis_client:
        return None
    
    try:
        raw_value = await redis_client.get(key)
        return await _decode_redis_bytes(raw_value)
    except redis.ConnectionError as e:
        logger.warning(f"_safe_redis_get: ошибка подключения к Redis для ключа {key}: {e}")
        return None
    except redis.TimeoutError as e:
        logger.warning(f"_safe_redis_get: таймаут Redis для ключа {key}: {e}")
        return None
    except Exception as e:
        logger.error(f"_safe_redis_get: неожиданная ошибка Redis для ключа {key}: {e}")
        return None


async def _safe_redis_delete(redis_client: Optional[redis.Redis], key: str) -> bool:
    """Безопасное удаление ключа из Redis с обработкой ошибок."""
    if not redis_client:
        return False
    
    try:
        await redis_client.delete(key)
        return True
    except redis.ConnectionError as e:
        logger.warning(f"_safe_redis_delete: ошибка подключения к Redis для ключа {key}: {e}")
        return False
    except redis.TimeoutError as e:
        logger.warning(f"_safe_redis_delete: таймаут Redis для ключа {key}: {e}")
        return False
    except Exception as e:
        logger.error(f"_safe_redis_delete: неожиданная ошибка Redis для ключа {key}: {e}")
        return False


async def _log_request_metrics(
    endpoint: str, 
    user_id: Optional[int], 
    request: Request, 
    success: bool, 
    duration_ms: Optional[float] = None,
    error_type: Optional[str] = None
):
    """Логирует метрики запросов для мониторинга."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    log_data = {
        "endpoint": endpoint,
        "user_id": user_id,
        "client_ip": client_ip,
        "user_agent": user_agent[:100],  # Ограничиваем длину
        "success": success,
        "method": request.method,
        "path": request.url.path
    }
    
    if duration_ms is not None:
        log_data["duration_ms"] = duration_ms
    
    if error_type:
        log_data["error_type"] = error_type
    
    if success:
        logger.info(f"Request metrics: {log_data}")
    else:
        logger.warning(f"Request metrics (error): {log_data}")


def _validate_file_upload(file: UploadFile, max_size_mb: int = 5) -> None:
    """Валидирует загружаемый файл."""
    if not file.content_type:
        raise ValidationError("Не удалось определить тип файла", field="photo")
    
    # Проверяем тип файла
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise ValidationError(
            f"Неподдерживаемый тип файла. Разрешены: {', '.join(allowed_types)}", 
            field="photo"
        )
    
    # Проверяем размер файла (если доступен)
    if hasattr(file, 'size') and file.size:
        max_size_bytes = max_size_mb * 1024 * 1024
        if file.size > max_size_bytes:
            raise ValidationError(
                f"Размер файла превышает {max_size_mb}MB", 
                field="photo"
            )

@router.get("/profile", response_model=UserProfile)
@require_cookie_and_not_deleted
@rate_limit(limit=10, period=60)
async def get_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis_client: Optional[redis.Redis] = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает профиль текущего пользователя.
    Сначала пытается получить профиль из кеша Redis. Если в кеше нет данных — читает профиль из базы данных.
    """
    cache_key = f"user:profile:{current_user.user_id}"

    # Пытаемся получить из кеша
    cached_data = await _safe_redis_get(redis_client, cache_key)
    if cached_data:
        try:
            return UserProfile(**json.loads(cached_data))
        except (json.JSONDecodeError, PydanticValidationError) as e:
            logger.warning(f"get_profile: поврежденный JSON в кеше для {cache_key}: {e}")
            await _safe_redis_delete(redis_client, cache_key)

    # fallback: из БД
    try:
        result = await db.execute(
            select(User).where(User.user_id == current_user.user_id, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()
        if user:
            # кешируем профиль
            try:
                await cache_user_profile(redis_client, user, cache_key, force=False)
            except Exception as e:
                logger.debug(f"get_profile: Не удалось закешировать профиль для {cache_key}: {e}")
            return UserProfile.from_orm(user)

        # если в БД нет (но в current_user он есть) — возвращаем current_user
        return UserProfile.from_orm(current_user)
    except Exception as e:
        logger.error(f"get_profile: Ошибка получения профиля user_id={current_user.user_id}: {e}")
        raise InternalServerError("Не удалось получить профиль пользователя")


@router.put("/profile", response_model=UserProfile)
@require_cookie_and_not_deleted
@not_banned_required
@rate_limit(limit=5, period=300)  # 5 запросов за 5 минут
async def update_profile(
    request: Request,
    user_login: Optional[str] = Form(None),
    user_full_name: Optional[str] = Form(None),
    user_email: Optional[EmailStr] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[redis.Redis] = Depends(get_redis),
):
    """
    Обновляет профиль текущего пользователя.
    Проверяет уникальность логина и email, сохраняет аватар.
    При изменении email создаёт запись в user_tokens и переводит статус в REGISTERED.
    """
    user_id = current_user.user_id
    updates = {}

    # Валидация входных данных
    if user_login is not None:
        user_login = user_login.strip()
        if len(user_login) < 3:
            raise ValidationError("Логин должен содержать минимум 3 символа", field="user_login")
        if len(user_login) > 50:
            raise ValidationError("Логин не может содержать более 50 символов", field="user_login")
        if user_login != current_user.user_login:
            q = select(User).where(
                User.user_login == user_login,
                User.user_id != user_id,
                User.is_deleted == False,
            )
            r = await db.execute(q)
            if r.scalar_one_or_none():
                raise ConflictError("Данный логин уже используется")
            updates["user_login"] = user_login

    if user_full_name is not None:
        user_full_name = user_full_name.strip()
        if len(user_full_name) > 100:
            raise ValidationError("Полное имя не может содержать более 100 символов", field="user_full_name")
        updates["user_full_name"] = user_full_name

    email_changed = False
    new_token_raw: Optional[str] = None
    if user_email is not None and user_email != current_user.user_email:
        q = select(User).where(
            User.user_email == user_email,
            User.user_id != user_id,
            User.is_deleted == False,
        )
        r = await db.execute(q)
        if r.scalar_one_or_none():
            raise ConflictError("Данный email уже используется")

        updates["user_email"] = user_email
        updates["status"] = UserStatus.REGISTERED
        email_changed = True

    if photo:
        _validate_file_upload(photo)
        try:
            avatar_filename = await save_uploaded_file(photo, user_id, settings.AVATAR_DIR, "user")
            updates["user_avatar_url"] = f"{avatar_filename}"
        except Exception as e:
            logger.error(f"Ошибка сохранения аватара user_id={user_id}: {e}")
            raise InternalServerError("Не удалось сохранить аватар")

    if updates:
        try:
            await db.execute(update(User).where(User.user_id == user_id).values(**updates))
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка обновления профиля user_id={user_id}: {e}")
            raise InternalServerError("Не удалось обновить профиль")

    # Если email изменился — создаём запись в user_tokens и отправляем письмо
    if email_changed:
        try:
            ttl = settings.TOKEN_TTL_SECONDS
            raw, _ = await create_token(db=db, user_id=user_id, token_type="email_verification", ttl=ttl)
            new_token_raw = raw
        except Exception as e:
            logger.error(f"Ошибка создания токена подтверждения при обновлении email user_id={user_id}: {e}")

    try:
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one()
    except Exception as e:
        logger.error(f"Ошибка получения обновленного пользователя user_id={user_id}: {e}")
        raise InternalServerError("Не удалось получить обновленный профиль")

    if email_changed and new_token_raw:
        try:
            await send_verification_email(user.user_email, user.user_full_name, new_token_raw)
        except Exception as e:
            logger.error(f"Не удалось отправить письмо подтверждения для user_id={user_id}: {e}")

    # Кешируем профиль
    if redis_client:
        try:
            await cache_user_profile(redis_client, user, f"user:profile:{user_id}", force=True)
        except Exception as e:
            logger.debug(f"Не удалось закешировать профиль после обновления для {user_id}: {e}")

    return UserProfile.from_orm(user)


@router.delete("/profile")
@require_cookie_and_not_deleted
@rate_limit(limit=3, period=3600)  # 3 запроса в час
async def delete_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[redis.Redis] = Depends(get_redis),
):
    """
    Мягкое удаление: помечает пользователя как удалённого, создаёт запись в user_tokens с типом 'account_restore'
    и (если есть email) отправляет письмо с сыром токеном для восстановления.
    """
    user_id = current_user.user_id

    try:
        # помечаем пользователя как удалённого
        await db.execute(update(User).where(User.user_id == user_id).values(is_deleted=True))
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Не удалось пометить пользователя как удалённого user_id={user_id}: {e}")
        raise InternalServerError("Не удалось удалить профиль")

    # создаём запись в user_tokens
    try:
        ttl = settings.TOKEN_TTL_SECONDS
        raw_token, _ = await create_token(db=db, user_id=user_id, token_type="account_restore", ttl=ttl)
    except Exception as e:
        logger.error(f"Не удалось создать токен восстановления для user_id={user_id}: {e}")
        raw_token = None

    if redis_client:
        await _safe_redis_delete(redis_client, f"user:profile:{user_id}")

    try:
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one()
        if user.user_email and raw_token:
            human_expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).astimezone().strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            )
            await send_deletion_email(user.user_email, user.user_full_name, raw_token, human_expires)
    except Exception as e:
        logger.error(f"Не удалось отправить письмо с восстановлением user_id={user_id}: {e}")

    return {"detail": "Пользователь успешно помечен как удалён. Письмо для восстановления отправлено (если указан email)."}


@router.post("/profile/restore")
@rate_limit(limit=5, period=3600)  # 5 попыток в час
async def restore_profile(
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[redis.Redis] = Depends(get_redis),
):
    """
    Восстанавливает мягко удалённый аккаунт по токену.
    Токен ищем в user_tokens (тип 'account_restore').
    """
    if not token:
        raise ValidationError("Токен обязателен", field="token")

    now = datetime.now(timezone.utc)
    token_hash = None
    try:
        token_hash = hash_token(token)
    except Exception as e:
        logger.error(f"Ошибка хеширования токена: {e}")
        raise ValidationError("Неверный формат токена", field="token")

    if not token_hash:
        raise ValidationError("Неверный токен", field="token")

    try:
        db_token = await get_token_by_hash(db, token_hash, "account_restore")
        if not db_token:
            raise NotFoundError("Токен восстановления")

        if db_token.expires_at and db_token.expires_at < now:
            raise ValidationError("Срок действия токена восстановления истёк", field="token")

        # получаем пользователя
        result = await db.execute(select(User).where(User.user_id == db_token.user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_deleted:
            raise NotFoundError("Пользователь для восстановления")

        await db.execute(
            update(User)
            .where(User.user_id == user.user_id)
            .values(
                is_deleted=False,
            )
        )
        await db.commit()
    except (ValidationError, NotFoundError):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка восстановления профиля user_id={user.user_id if 'user' in locals() else 'unknown'}: {e}")
        raise InternalServerError("Не удалось восстановить профиль")

    # помечаем токен использованным
    try:
        await consume_user_token(db, db_token)
    except Exception as e:
        logger.warning(f"Не удалось пометить токен как использованный user_id={user.user_id}: {e}")

    if redis_client:
        try:
            # получаем свежую запись из БД и принудительно перезаписываем кеш
            result = await db.execute(select(User).where(User.user_id == user.user_id))
            fresh_user = result.scalar_one()
            await cache_user_profile(redis_client, fresh_user, f"user:profile:{user.user_id}", force=True)
        except Exception as e:
            logger.debug(f"Не удалось закешировать профиль после восстановления для {user.user_id}: {e}")

    try:
        await send_email(
            to=user.user_email,
            subject="Аккаунт восстановлен",
            body=f"""
                <p>Здравствуйте, {user.user_full_name}!</p>
                <p>Ваш аккаунт был успешно восстановлен.</p>
            """,
        )
    except Exception as e:
        logger.error(f"Не удалось отправить подтверждение восстановления user_id={user.user_id}: {e}")

    return {"detail": "Аккаунт успешно восстановлен"}


@router.get("/search", response_model=List[UserProfile])
@require_cookie_and_not_deleted
@not_banned_required
@rate_limit(limit=20, period=60)  # 20 запросов в минуту
async def search_users(
    request: Request,
    user_login: Optional[str] = None,
    user_full_name: Optional[str] = None,
    user_email: Optional[str] = None,
    role_id: Optional[int] = None,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ищет пользователей по переданным фильтрам (логин, имя, email, роль)."""
    
    # Валидация параметров
    if limit < 1 or limit > 100:
        raise ValidationError("Лимит должен быть от 1 до 100", field="limit")
    
    q = select(User).where(User.is_deleted == False)
    
    # Безопасный поиск с экранированием специальных символов
    if user_login:
        # Ограничиваем длину и экранируем специальные символы
        user_login = user_login.strip()[:50]  # Максимум 50 символов
        if len(user_login) < 2:  # Минимум 2 символа для поиска
            raise ValidationError("Поиск по логину требует минимум 2 символа", field="user_login")
        q = q.filter(User.user_login.ilike(f"%{user_login}%"))
        
    if user_full_name:
        user_full_name = user_full_name.strip()[:100]  # Максимум 100 символов
        if len(user_full_name) < 2:
            raise ValidationError("Поиск по имени требует минимум 2 символа", field="user_full_name")
        q = q.filter(User.user_full_name.ilike(f"%{user_full_name}%"))
        
    if user_email and current_user.role_id in (1, 2):  # Только для админов/модераторов
        user_email = user_email.strip()[:100]
        if len(user_email) < 3:
            raise ValidationError("Поиск по email требует минимум 3 символа", field="user_email")
        q = q.filter(User.user_email.ilike(f"%{user_email}%"))
    elif user_email and current_user.role_id not in (1, 2):
        raise AuthorizationError("Поиск по email доступен только администраторам и модераторам")
        
    if role_id and current_user.role_id in (1, 2):  # Только для админов/модераторов
        if role_id not in (1, 2, 3):
            raise ValidationError("Неверная роль", field="role_id")
        q = q.filter(User.role_id == role_id)
    elif role_id and current_user.role_id not in (1, 2):
        raise AuthorizationError("Фильтрация по роли доступна только администраторам и модераторам")

    try:
        result = await db.execute(q.order_by(User.user_login).limit(limit))
        users = result.scalars().all()
        return [UserProfile.from_orm(u) for u in users]
    except Exception as e:
        logger.error(f"Ошибка поиска пользователей: {e}")
        raise InternalServerError("Не удалось выполнить поиск пользователей")


@router.get("/{user_id}", response_model=UserProfile)
@require_cookie_and_not_deleted
@not_banned_required
@rate_limit(limit=30, period=60)  # 30 запросов в минуту
async def get_user_profile(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[redis.Redis] = Depends(get_redis),
):
    """Возвращает профиль пользователя по ID."""

    # Валидация user_id
    if user_id < 1:
        raise ValidationError("ID пользователя должен быть положительным числом", field="user_id")

    cache_key = f"user:profile:{user_id}"

    # сначала попробуем отдать из кеша
    cached_data = await _safe_redis_get(redis_client, cache_key)
    if cached_data:
        try:
            return UserProfile(**json.loads(cached_data))
        except (json.JSONDecodeError, PydanticValidationError) as e:
            logger.warning(f"get_user_profile: поврежденный JSON в кеше для {cache_key}: {e}")
            await _safe_redis_delete(redis_client, cache_key)

    # fallback: из БД
    try:
        result = await db.execute(select(User).where(User.user_id == user_id, User.is_deleted == False))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("Пользователь")

        # кешируем "без force" — установится только если ключа нет
        try:
            await cache_user_profile(redis_client, user, cache_key, force=False)
        except Exception as e:
            logger.debug(f"Не удалось закешировать профиль для {user_id}: {e}")

        return UserProfile.from_orm(user)
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения профиля пользователя user_id={user_id}: {e}")
        raise InternalServerError("Не удалось получить профиль пользователя")


@router.post("/profile/reset-password/request")
@require_cookie_and_not_deleted
@rate_limit(limit=3, period=3600)  # 3 запроса в час
async def request_password_reset(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Авторизованный пользователь запрашивает сброс пароля. Письмо уходит на его email из БД."""
    if not current_user.user_email:
        raise ValidationError("У пользователя не указан email", field="user_email")

    try:
        ttl = settings.RESET_PASSWORD_TTL_SECONDS
        raw_token, _ = await create_token(db=db, user_id=current_user.user_id, token_type="password_reset", ttl=ttl)
    except Exception as e:
        logger.error(f"Ошибка создания токена сброса пароля user_id={current_user.user_id}: {e}")
        raise InternalServerError("Не удалось запросить сброс пароля")

    human_expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    # Формируем ссылку для фронтенда
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={quote_plus(raw_token)}"
    try:
        await send_reset_password(
            current_user.user_email,
            current_user.user_full_name,
            raw_token,
            human_expires,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки письма сброса пароля user_id={current_user.user_id}: {e}")

    return {"detail": "Инструкция по сбросу пароля отправлена на ваш email"}


@router.post("/profile/reset-password/confirm")
@rate_limit(limit=5, period=3600)  # 5 попыток в час
async def confirm_password_reset(
    token: str = Form(...),
    new_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Подтверждает сброс пароля по токену из письма и устанавливает новый пароль.
    Гарантирует: токен одноразовый — помечается consumed_at атомарно вместе с обновлением пароля.
    """
    # Валидация пароля
    if len(new_password) < 8:
        raise ValidationError("Пароль должен содержать минимум 8 символов", field="new_password")
    if len(new_password) > 128:
        raise ValidationError("Пароль не может содержать более 128 символов", field="new_password")

    now = datetime.now(timezone.utc)
    try:
        token_hash = hash_token(token)
    except Exception as e:
        logger.error(f"Ошибка хеширования токена сброса пароля: {e}")
        raise ValidationError("Неверный формат токена", field="token")

    try:
        async with db.begin():
            # Выбираем token с блокировкой
            q = select(UserToken).where(
                UserToken.token_hash == token_hash,
                UserToken.token_type == "password_reset"
            ).with_for_update()
            res = await db.execute(q)
            db_token = res.scalar_one_or_none()

            if not db_token:
                raise NotFoundError("Токен сброса пароля")

            if db_token.expires_at and db_token.expires_at < now:
                raise ValidationError("Срок действия токена истёк", field="token")
            if db_token.consumed_at is not None:
                raise ValidationError("Токен уже был использован", field="token")

            # Берём пользователя и блокируем его строку
            q2 = select(User).where(User.user_id == db_token.user_id).with_for_update()
            res2 = await db.execute(q2)
            user = res2.scalar_one_or_none()
            if not user or user.is_deleted:
                raise NotFoundError("Пользователь")

            # Обновляем пароль и помечаем токен как использованный (обе операции в транзакции)
            new_hashed = hash_password_with_pepper(new_password, settings.PASSWORD_PEPPER or "")
            # присваиваем ORM-объектам — это будет учтено при коммите транзакции
            user.user_password_hash = new_hashed
            db_token.consumed_at = now

    except (ValidationError, NotFoundError):
        raise
    except Exception as e:
        logger.error(f"confirm_password_reset: unexpected error: {e}")
        raise InternalServerError("Ошибка сервера при подтверждении сброса пароля")

    return {"detail": "Пароль успешно изменён"}
