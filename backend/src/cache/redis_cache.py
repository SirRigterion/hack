import asyncio
import json
from typing import Optional, Any, Callable, Tuple
import redis.asyncio as redis
import functools
import hashlib

from src.core.config_app import settings
from src.core.config_log import logger


redis_client: Optional[redis.Redis] = None

PING_TIMEOUT = 1.0     # быстрая проверка жив ли клиент
ERROR_SNOOZE = 60      # секунды между ERROR-логами о Redis (чтобы не спамить)
RECONNECT_INTERVAL = 60  # интервал для реконнектора

async def init_redis(max_attempts: int = 3, delay: int = 2) -> None:
    """Пробуем подключиться к Redis при старте (несколько попыток)."""
    global redis_client
    attempt = 1
    while attempt <= max_attempts:
        try:
            client = redis.from_url(settings.REDIS_URL, decode_responses=False)
            await asyncio.wait_for(client.ping(), timeout=5.0)
            redis_client = client
            logger.info("init_redis: Подключение к Redis успешно")
            return
        except Exception as e:
            logger.warning(f"init_redis: попытка {attempt}/{max_attempts} не удалась: {e}")
            redis_client = None
            if attempt == max_attempts:
                logger.error("init_redis: Redis недоступен, продолжаем работу без него")
                return
            await asyncio.sleep(delay)
            attempt += 1

async def get_redis() -> Optional[redis.Redis]:
    """Возвращает живой redis-клиент или None. При падении клиента — отключает и подавляет спам логов."""
    global redis_client
    if redis_client is None:
        return None
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=PING_TIMEOUT)
        return redis_client
    except Exception as e:
        logger.error(f"get_redis: Redis отключен из-за ошибки: {e}")
        try:
            await redis_client.close()
        except Exception:
            pass
        redis_client = None
        return None

# низкоуровневые операции
async def get_bytes(key: str) -> Optional[bytes]:
    r = await get_redis()
    if r is None:
        logger.debug(f"get_bytes: Redis недоступен, пропускаем для ключа {key}")
        return None
    try:
        raw = await r.get(key)
        if raw is not None:
            logger.debug(f"get_bytes: Успешно получен ключ {key}")
        return raw
    except Exception as e:
        logger.error(f"get_bytes: Ошибка получения ключа {key}: {e}")
        try:
            await r.close()
        except Exception:
            pass
        global redis_client
        redis_client = None
        return None

async def set_bytes(key: str, data: bytes, ttl: int) -> bool:
    r = await get_redis()
    if r is None:
        logger.debug(f"set_bytes: Redis недоступен, пропускаем запись для ключа {key}")
        return False
    try:
        await r.setex(key, ttl, data)
        logger.debug(f"set_bytes: Успешно записан ключ {key} с TTL {ttl}")
        return True
    except Exception as e:
        logger.error(f"set_bytes: Ошибка записи ключа {key}: {e}")
        try:
            await r.close()
        except Exception:
            pass
        global redis_client
        redis_client = None
        return False

async def delete(key: str) -> bool:
    r = await get_redis()
    if r is None:
        logger.debug(f"delete: Redis недоступен, пропускаем удаление для ключа {key}")
        return False
    try:
        deleted = await r.delete(key)
        if deleted > 0:
            logger.debug(f"delete: Успешно удален ключ {key}")
        return True
    except Exception as e:
        logger.error(f"delete: Ошибка удаления ключа {key}: {e}")
        try:
            await r.close()
        except Exception:
            pass
        global redis_client
        redis_client = None
        return False

async def incr(key: str, amount: int = 1, ttl: Optional[int] = None) -> Optional[int]:
    r = await get_redis()
    if r is None:
        logger.debug(f"incr: Redis недоступен, пропускаем инкремент для ключа {key}")
        return None
    try:
        new = await r.incrby(key, amount)
        if ttl is not None:
            await r.expire(key, ttl)
        logger.debug(f"incr: Успешно инкрементирован ключ {key} до {new}")
        return int(new)
    except Exception as e:
        logger.error(f"incr: Ошибка инкремента {key}: {e}")
        try:
            await r.close()
        except Exception:
            pass
        global redis_client
        redis_client = None
        return None

async def get_data(key: str) -> Optional[Any]:
    """Получает данные по ключу с десериализацией (только JSON)."""
    raw = await get_bytes(key)
    if raw is None:
        return None
    try:
        decoded = raw.decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"get_data: Ошибка десериализации для ключа {key}: {e}")
        return None

async def set_data(key: str, obj: Any, ttl: int) -> bool:
    """Сохраняет данные по ключу с сериализацией (только JSON)."""
    try:
        raw = json.dumps(obj, default=str).encode("utf-8")
    except Exception as e:
        logger.error(f"set_data: Ошибка сериализации для ключа {key}: {e}")
        return False
    return await set_bytes(key, raw, ttl)

async def set_if_not_exists(redis_client: Optional[redis.Redis], key: str, value: bytes, ttl: int) -> bool:
    """
    Установить ключ только если он не существует (NX) с TTL (EX).
    Возвращает True если ключ установлен, False если ключ уже есть или при ошибке.
    """
    if not redis_client:
        return False
    try:
        res = await redis_client.set(key, value, ex=int(ttl), nx=True)
        return bool(res)
    except Exception as e:
        logger.error(f"set_if_not_exists: Ошибка записи ключа {key}: {e}")
        await redis_client.close()

        # не трогаем глобальный redis_client здесь — он управляется в модуле инициализации
        return False


async def cache_user_profile(
    redis_client: Optional[redis.Redis],
    user_obj: Any,
    cache_key: Optional[str] = None,
    force: bool = False,
) -> bool:
    """
    Кэширует профиль пользователя в Redis.

    - redis_client: экземпляр redis.asyncio.Redis или None.
    - user_obj: ORM-объект User (или любой объект, совместимый с UserProfile.from_orm).
    - cache_key: ключ в Redis (если None — будет сформирован как 'user:profile:{user_id}').
    - force: если True — всегда перезаписать (SETEX). Если False — попытаться установить атомарно (SET NX EX)
             и если ключ уже есть — пропустить запись.

    Возвращает True если запись успешна или пропущена (key already exists), False при ошибке.
    """
    if not redis_client:
        return False

    # Импортируем UserProfile локально, чтобы избежать циклического импорта
    from src.users.schemas import UserProfile

    try:
        profile = UserProfile.from_orm(user_obj) # type: ignore
    except Exception:
        try:
            profile = UserProfile.parse_obj(user_obj)  # type: ignore
        except Exception as e:
            logger.error(f"cache_user_profile: не удалось сериализовать профиль: {e}")
            return False

    if cache_key is None:
        try:
            user_id = getattr(user_obj, "user_id")
            cache_key = f"user:profile:{user_id}"
        except Exception:
            logger.error("cache_user_profile: не удалось определить user_id для формирования cache_key")
            return False

    try:
        payload_str = json.dumps(profile.dict(by_alias=True), default=str)
        payload_bytes = payload_str.encode("utf-8")
    except Exception as e:
        logger.error(f"cache_user_profile: ошибка сериализации профиля для {cache_key}: {e}")
        return False

    if not force:
        try:
            existing = await redis_client.get(cache_key)
        except Exception as e:
            logger.debug(f"cache_user_profile: ошибка чтения ключа {cache_key}: {e}")
            existing = None

        if existing is not None:
            logger.debug(f"cache_user_profile: cache hit, skip set for {cache_key}")
            return True

        try:
            did_set = await set_if_not_exists(redis_client, cache_key, payload_bytes, settings.REDIS_TTL)
            if did_set:
                logger.debug(f"cache_user_profile: Профиль записан (NX): {cache_key}")
                return True
            else:
                logger.debug(f"cache_user_profile: Ключ уже появился, пропускаем запись: {cache_key}")
                return True
        except Exception as e:
            logger.error(f"cache_user_profile: ошибка установки NX для {cache_key}: {e}")
            return False

    else:
        try:
            await redis_client.setex(cache_key, int(settings.REDIS_TTL), payload_bytes)
            logger.debug(f"cache_user_profile: Профиль перезаписан (force): {cache_key}")
            return True
        except Exception as e:
            logger.error(f"cache_user_profile: ошибка SETEX для {cache_key}: {e}")
            return False
    
def cache_async(ttl: int, key_prefix: str = "", ignore_args: Tuple[str, ...] = ()):
    """
    Декоратор для асинхронного кэширования результатов функций.
    - ttl: время жизни кэша в секундах
    - key_prefix: префикс для ключа (если не указан, использует имя функции)
    - ignore_args: кортеж имен аргументов, которые игнорируются при формировании ключа
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not key_prefix:
                prefix = f"{func.__module__}.{func.__name__}"
            else:
                prefix = key_prefix

            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ignore_args}

            args_str = str(args) + str(filtered_kwargs)
            args_hash = hashlib.sha256(args_str.encode()).hexdigest()
            cache_key = f"{prefix}:{args_hash}"

            cached = await get_data(cache_key)
            if cached is not None:
                logger.debug(f"cache_async: Хит кэша для {cache_key}")
                return cached

            result = await func(*args, **kwargs)

            success = await set_data(cache_key, result, ttl=ttl)
            if success:
                logger.debug(f"cache_async: Кэш сохранен для {cache_key}")
            else:
                logger.warning(f"cache_async: Не удалось сохранить кэш для {cache_key}")

            return result
        return wrapper
    return decorator