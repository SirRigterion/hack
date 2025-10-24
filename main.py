from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from src.users.routes import router as users_router
from src.admin.routes import router as admin_router
from src.moder.routes import router as moder_router
from src.auth.routes import router as auth_router
from src.images.routes import router as img_router
from src.chat.routes import router as chat_router
from src.video.routes import router as video_router
from src.db.database import engine, startup as db_startup
from src.db.models import Role, User, UserStatus
from src.utils.password import hash_password_with_pepper
from src.core.config_app import settings
from src.core.config_log import logger
from src.core.exceptions import setup_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск приложения начат")

    await db_startup()
    logger.info("Подключение к PostgeSQL и Redis завершено")

    async with engine.begin() as conn:
        # роли
        desired_roles = [
            {"role_id": 1, "role_name": "администратор"},
            {"role_id": 2, "role_name": "модератор"},
            {"role_id": 3, "role_name": "пользователь"},
        ]

        res = await conn.execute(select(Role.role_id))
        existing_role_ids = set(res.scalars().all())

        missing = [r for r in desired_roles if r["role_id"] not in existing_role_ids]
        if missing:
            # вставляем недостающие роли
            await conn.execute(Role.__table__.insert(), missing)
            logger.info(f"Созданы недостающие роли: {[r['role_id'] for r in missing]}")
        else:
            logger.debug("Роли уже присутствуют в БД")

        # админ: создаём, если нет пользователя с user_id = 1
        res = await conn.execute(select(User).where(User.user_id == 1))
        existing_admin = res.scalars().first()
        if not existing_admin:
            if not settings.ADMIN_PASSWORD:
                logger.error("ADMIN_PASSWORD не задан в настройках — админ не будет создан")
            else:
                # Не логируем пароль администратора
                logger.info("Создание администратора по умолчанию")
                hashed = hash_password_with_pepper(settings.ADMIN_PASSWORD, settings.PASSWORD_PEPPER)

                # Используем имя файла аватара из настроек
                admin_avatar_name = settings.ADMIN_IMAGES
                
                insert_stmt = User.__table__.insert().values(
                    user_login="admin",
                    user_full_name="Админ Админов",
                    user_email=settings.ADMIN_EMAIL,
                    user_password_hash=hashed,
                    user_salt="",  # Больше не используем отдельную соль
                    user_avatar_url=admin_avatar_name,
                    role_id=1,
                    registered_at=func.now(),
                    is_deleted=False,
                    status=UserStatus.ACTIVE, 
                    ban_reason=None,
                    banned_at=None,
                )

                await conn.execute(insert_stmt)
                logger.info("Администратор по умолчанию создан")
        else:
            logger.debug("Администратор по id = 1 уже существует")

    yield  # — здесь приложение «живет»

    logger.info("Завершение работы приложения начато")
    await engine.dispose()
    logger.info("Соединение с БД закрыто")
    logger.info("Приложение полностью остановлено")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# Настраиваем обработчики исключений
setup_exception_handlers(app)

app.include_router(users_router)
app.include_router(admin_router)
app.include_router(moder_router)
app.include_router(auth_router)
app.include_router(img_router)
app.include_router(chat_router)
app.include_router(video_router)

# Статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True
    )
