import os
from typing import Optional
from dotenv import find_dotenv, load_dotenv
from urllib.parse import quote

from .config_log import logger


class Settings:
    PROJECT_NAME = "UserAPI by ARig"
    PROJECT_VERSION = "8.0.0-docker"

    def __init__(self):
        if not load_dotenv(find_dotenv(), override=True):
            raise RuntimeError(f"Не удалось загрузить .env файл")

        self.POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
        self.POSTGRES_PASSWORD: Optional[str] = os.getenv("POSTGRES_PASSWORD")
        self.POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "db")
        self.POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
        self.POSTGRES_DB: str = os.getenv("POSTGRES_DB", "db")

        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.REDIS_TTL: int = int(os.getenv("REDIS_TTL", 600))
        
        self.ALLOWED_ORIGINS: list = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        self.SECRET_KEY: str = os.getenv("SECRET_KEY")
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.PASSWORD_PEPPER: str = os.getenv("PASSWORD_PEPPER")
        self.ACCESS_TOKEN_EXPIRE_SECONDS: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_SECONDS", 15))

        self.UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", ".\\uploads")
        self.AVATAR_DIR: str = os.getenv("AVATAR_DIR", ".\\avatars")
        
        self.ADMIN_IMAGES: str = os.getenv("ADMIN_IMAGES", "user-1-admin.jpg")
        self.ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
        self.ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@example.com")

        self.COOKIE_MODE: bool = os.getenv("COOKIE_MODE", "false").lower() == "true"         # 1 - защещённый, 0 - не защещёный

        self.SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", 465))
        self.SMTP_USER: str = os.getenv("SMTP_USER")
        self.SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD")
        self.SMTP_FROM: str = os.getenv("SMTP_FROM", self.SMTP_USER)
        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
        
        self.TOKEN_TTL_SECONDS: int = int(os.getenv("TOKEN_TTL_SECONDS", 86400))
        self.TOKEN_RESEND_MAX: int = int(os.getenv("TOKEN_RESEND_MAX", 5))
        self.TOKEN_RESEND_WINDOW_SECONDS: int = int(os.getenv("TOKEN_RESEND_WINDOW_SECONDS", 86400))
        self.RESET_PASSWORD_TTL_SECONDS: int = int(os.getenv("RESET_PASSWORD_TTL_SECONDS", 86400))
        
        self.IMAGE_CACHE_TTL: int = int(os.getenv("IMAGE_CACHE_TTL", 3600))
        self.IMAGE_CACHE_MAX_BYTES: int = int(os.getenv("IMAGE_CACHE_MAX_BYTES", 500000))

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Формирует URL для асинхронного подключения к базе данных."""
        password = quote(self.POSTGRES_PASSWORD) if self.POSTGRES_PASSWORD else ""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Формирует URL для синхронного подключения к базе данных."""
        password = quote(self.POSTGRES_PASSWORD) if self.POSTGRES_PASSWORD else ""
        return (
            f"postgresql://{self.POSTGRES_USER}:{password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def __post_init__(self):
        """Проверяет критические настройки после инициализации."""
        if not self.SECRET_KEY:
            logger.error("SECRET_KEY не задан в переменных окружения")
            raise ValueError("SECRET_KEY должен быть задан")
        if not self.PASSWORD_PEPPER:
            logger.error("PASSWORD_PEPPER не задан в переменных окружения")
            raise ValueError("SECRET_KEY должен быть задан")
        if not self.POSTGRES_DB:
            logger.error("POSTGRES_DB не задан в переменных окружения")
            raise ValueError("POSTGRES_DB должен быть задан")
        # logger.debug(f"Async Database URL: {settings.ASYNC_DATABASE_URL}")
        # logger.debug(f"Sync Database URL: {settings.SYNC_DATABASE_URL}")
        # logger.debug(type(settings.COOKIE_MODE))
        # logger.debug(settings.COOKIE_MODE)


settings = Settings()
