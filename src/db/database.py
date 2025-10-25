import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import text

from src.cache.redis_cache import init_redis
from src.core.config_app import settings
from src.core.config_log import logger


# Настройки безопасности для движка базы данных
engine = create_async_engine(
    settings.ASYNC_DATABASE_URL, 
    echo=False,
    pool_size=10,  # Ограничиваем размер пула соединений
    max_overflow=20,  # Максимальное количество дополнительных соединений
    pool_timeout=30,  # Таймаут получения соединения
    pool_recycle=3600,  # Переиспользование соединений каждый час
    pool_pre_ping=True,  # Проверка соединений перед использованием
    connect_args={
        "command_timeout": 30,  # Таймаут команд
        "server_settings": {
            "application_name": "UserAPI",
            "statement_timeout": "30s",  # Таймаут выполнения запросов
            "idle_in_transaction_session_timeout": "60s"  # Таймаут транзакций
        }
    }
)

async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autoflush=True,
    autocommit=False
)
Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Предоставляет сессию базы данных."""
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Ошибка в сессии базы данных: {e}")
            raise
        finally:
            await session.close()

async def test_db_connection(max_attempts=3, delay=2) -> None:
    """Проверяет подключение к базе данных."""
    attempt = 1
    while attempt <= max_attempts:
        try:
            async with engine.connect() as conn:
                result = await conn.scalar(text("SELECT 1"))
                if result != 1:
                    raise ValueError("Неожиданный результат тестового запроса к базе данных")
            logger.info("Подключение к базе данных успешно")
            return
        except Exception as e:
            logger.warning(f"Попытка {attempt}/{max_attempts} подключения к БД не удалась: {e}")
            if attempt == max_attempts:
                raise
            await asyncio.sleep(delay)
            attempt += 1
            

async def startup() -> None:
    """Инициализирует подключения при старте приложения."""
    await test_db_connection()
    await init_redis()