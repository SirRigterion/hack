import asyncio
from functools import wraps
from fastapi import Request, HTTPException, status
from typing import Callable, Any, TypeVar

from src.db.models import User, UserStatus
from src.core.config_log import logger
from src.cache.redis_cache import incr

F = TypeVar("F", bound=Callable[..., Any])

suspicious_activity = {}


def _find_request_and_user(args, kwargs):
    """Вспомогательная: ищет Request и User среди args/kwargs."""
    request = kwargs.get("request")
    if not request:
        for a in args:
            if isinstance(a, Request):
                request = a
                break

    current_user = kwargs.get("current_user")
    if not current_user:
        for a in args:
            if isinstance(a, User):
                current_user = a
                break

    return request, current_user


def require_cookie_and_not_deleted(func: F) -> F:
    """
    Декоратор для FastAPI-эндпоинтов:
    1. Проверяет наличие куки 'access_token'.
    2. Проверяет, что пользователь не удалён.
    3. Отслеживает подозрительную активность.
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        request, current_user = _find_request_and_user(args, kwargs)

        if not request:
            logger.error("require_cookie_and_not_deleted: объект Request не найден")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Internal error: Request object not found")

        # Отслеживаем подозрительную активность
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Проверяем на подозрительные паттерны
        suspicious_patterns = [
            "sqlmap", "nmap", "nikto", "burp", "w3af", "havij", 
            "sqlninja", "pangolin", "sqlsus", "r00t", "hack"
        ]
        
        if any(pattern in user_agent.lower() for pattern in suspicious_patterns):
            logger.warning(f"Подозрительный User-Agent: {user_agent} от IP: {client_ip}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен")

        token = request.cookies.get("access_token")
        if not token:
            # Отслеживаем попытки доступа без токена
            key = f"no_token:{client_ip}"
            suspicious_activity[key] = suspicious_activity.get(key, 0) + 1
            
            if suspicious_activity[key] > 10:  # Более 10 попыток за сессию
                logger.warning(f"Множественные попытки доступа без токена от IP: {client_ip}")
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
                                  detail="Слишком много попыток доступа")
            
            logger.warning(f"require_cookie_and_not_deleted: нет access_token, IP={client_ip}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Требуется аутентификация",
                                headers={"WWW-Authenticate": "Bearer"})
        
        logger.debug(f"require_cookie_and_not_deleted: access_token найден, IP={client_ip}")

        if not current_user:
            logger.error("require_cookie_and_not_deleted: current_user отсутствует")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")

        if getattr(current_user, "is_deleted", False):
            logger.warning(f"require_cookie_and_not_deleted: удалённый пользователь user_id={current_user.user_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ваш аккаунт удалён")
        
        logger.debug(f"require_cookie_and_not_deleted: пользователь user_id={current_user.user_id} активен")

        return await func(*args, **kwargs)

    def sync_wrapper(*args, **kwargs):
        request, current_user = _find_request_and_user(args, kwargs)

        if not request:
            logger.error("require_cookie_and_not_deleted (sync): объект Request не найден")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Internal error: Request object not found")

        token = request.cookies.get("access_token")
        if not token:
            logger.warning(f"require_cookie_and_not_deleted (sync): нет access_token, IP={request.client.host}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Требуется аутентификация",
                                headers={"WWW-Authenticate": "Bearer"})
        logger.debug(f"require_cookie_and_not_deleted (sync): access_token найден, IP={request.client.host}")

        if not current_user:
            logger.error("require_cookie_and_not_deleted (sync): current_user отсутствует")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")

        if getattr(current_user, "is_deleted", False):
            logger.warning(f"require_cookie_and_not_deleted (sync): удалённый пользователь user_id={current_user.user_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ваш аккаунт удалён")
        logger.debug(f"require_cookie_and_not_deleted (sync): пользователь user_id={current_user.user_id} активен")

        return func(*args, **kwargs)

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


def rate_limit(limit: int = 5, period: int = 60) -> Callable[[F], F]:
    """
    Декоратор для FastAPI-эндпоинтов:
    Ограничивает число запросов по пользователю: не более `limit` вызовов за `period` секунд.

    Использует `incr` из src.cache.redis_cache.
    Fail-open: если Redis недоступен, вызов не блокируется.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            _, current_user = _find_request_and_user(args, kwargs)

            if current_user:
                key = f"user:{current_user.user_id}:{func.__name__}"
                try:
                    new_val = await incr(key, amount=1, ttl=period)
                except Exception as e:
                    logger.warning(f"rate_limit: Redis error for user_id={current_user.user_id}: {e}")
                    new_val = None

                if new_val is None:
                    # Redis недоступен — fail-open
                    logger.debug(f"rate_limit: Redis недоступен, пропускаем rate-limit для user_id={current_user.user_id}")
                else:
                    try:
                        if int(new_val) == 1:
                            logger.debug(f"rate_limit: установлено новое ограничение для user_id={current_user.user_id}, limit={limit}/{period}s")
                        if int(new_val) > limit:
                            logger.warning(f"rate_limit: превышен лимит для user_id={current_user.user_id}, count={new_val}, limit={limit}")
                            raise HTTPException(
                                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail=f"Превышено число запросов (не более {limit} за {period}s)"
                            )
                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.error(f"rate_limit: unexpected error while checking limit for user_id={current_user.user_id}: {e}")

            # Если current_user отсутствует — пропускаем проверку
            return await func(*args, **kwargs)

        return wrapper
    return decorator



def not_banned_required(func):
    """
    Декоратор для FastAPI-эндпоинтов:
    Проверяет, что пользователь не заблокирован (status != BANNED).
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        _, current_user = _find_request_and_user(args, kwargs)
        if not current_user:
            logger.error("not_banned_required: current_user отсутствует")
            raise HTTPException(status_code=403, detail="Доступ запрещён. Пользователь не найден.")
        if getattr(current_user, "status", None) == UserStatus.BANNED:
            logger.warning(f"not_banned_required: забаненный пользователь user_id={current_user.user_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ваш аккаунт заблокирован")

        logger.debug(f"not_banned_required: пользователь user_id={current_user.user_id} не забанен")
        return await func(*args, **kwargs)
    return wrapper


def admin_required(func):
    """
    Декоратор для FastAPI-эндпоинтов:
    Проверяет, что пользователь имеет роль Администратор (1).
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        _, current_user = _find_request_and_user(args, kwargs)
        if not current_user:
            logger.error("admin_required: current_user отсутствует")
            raise HTTPException(status_code=403, detail="Доступ запрещён. Только админы.")
        if current_user.role_id != 1:
            logger.warning(f"admin_required: доступ запрещён для user_id={current_user.user_id}, role_id={current_user.role_id}")
            raise HTTPException(status_code=403, detail="Доступ запрещён. Только админы.")
        logger.debug(f"admin_required: доступ разрешён user_id={current_user.user_id}")
        return await func(*args, **kwargs)
    return wrapper


def moder_required(func):
    """
    Декоратор для FastAPI-эндпоинтов:
    Проверяет, что пользователь имеет роль Администратор (1) или Модератор (2).
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        _, current_user = _find_request_and_user(args, kwargs)
        if not current_user:
            logger.error("moder_required: current_user отсутствует")
            raise HTTPException(status_code=403, detail="Доступ запрещён. Только модераторы или админы.")
        if current_user.role_id not in (1, 2):
            logger.warning(f"moder_required: доступ запрещён для user_id={current_user.user_id}, role_id={current_user.role_id}")
            raise HTTPException(status_code=403, detail="Доступ запрещён. Только модераторы или админы.")
        logger.debug(f"moder_required: доступ разрешён user_id={current_user.user_id}")
        return await func(*args, **kwargs)
    return wrapper
