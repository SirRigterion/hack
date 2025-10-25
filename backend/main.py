import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from src.users.routes import profile_router, admin_router, moder_router, public_router
from src.websocket.routes import router as websocket_router
from src.websocket.auth import router as websocket_auth_router
from src.auth.routes import router as auth_router
from src.images.routes import router as img_router
from src.chat.routes import router as chat_router
from src.db.database import engine, startup as db_startup
from src.db.models import Role, User, UserStatus
from src.auth.auth import get_current_user
from src.utils.password import hash_password_with_pepper
from src.core.config_app import settings
from src.core.config_log import logger
from src.core.exceptions import setup_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск приложения начат")

    await db_startup()
    logger.info("Подключение к PostgreSQL и Redis завершено")

    async with engine.begin() as conn:
        # Создаем роли если их нет
        desired_roles = [
            {"role_id": 1, "role_name": "администратор"},
            {"role_id": 2, "role_name": "модератор"},
            {"role_id": 3, "role_name": "пользователь"},
        ]

        res = await conn.execute(select(Role.role_id))
        existing_role_ids = set(res.scalars().all())

        missing = [r for r in desired_roles if r["role_id"] not in existing_role_ids]
        if missing:
            await conn.execute(Role.__table__.insert(), missing)
            logger.info(f"Созданы недостающие роли: {[r['role_id'] for r in missing]}")
        else:
            logger.debug("Роли уже присутствуют в БД")

        # Создаем администратора по умолчанию если его нет
        res = await conn.execute(select(User).where(User.user_id == 1))
        existing_admin = res.scalars().first()
        if not existing_admin:
            if not settings.ADMIN_PASSWORD:
                logger.error("ADMIN_PASSWORD не задан в настройках — админ не будет создан")
            else:
                logger.info("Создание администратора по умолчанию")
                hashed = hash_password_with_pepper(settings.ADMIN_PASSWORD, settings.PASSWORD_PEPPER)

                admin_avatar_name = settings.ADMIN_IMAGES

                insert_stmt = User.__table__.insert().values(
                    user_login="admin",
                    user_full_name="Админ Админов",
                    user_email=settings.ADMIN_EMAIL,
                    user_password_hash=hashed,
                    user_salt="",
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

    yield

    logger.info("Завершение работы приложения начато")
    await engine.dispose()
    logger.info("Соединение с БД закрыто")
    logger.info("Приложение полностью остановлено")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# Настраиваем обработчики исключений
setup_exception_handlers(app)

# Подключаем роутеры с новой структурой пользователей
app.include_router(profile_router, prefix="/users")
app.include_router(admin_router, prefix="/users")
app.include_router(moder_router, prefix="/users")
app.include_router(public_router, prefix="/users")

# Остальные роутеры
app.include_router(auth_router)
app.include_router(img_router)

app.include_router(websocket_auth_router)
app.include_router(websocket_router, prefix="/api/v1")

# Статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# Настраиваем шаблоны
templates = Jinja2Templates(directory="templates")

@app.get("/room/{room_code}", response_class=HTMLResponse)
async def video_room(request: Request, room_code: str):
    """
    Страница конкретной видео комнаты
    """
    return templates.TemplateResponse("video_call.html", {"request": request, "room_code": room_code})


@app.get("/test-video", response_class=HTMLResponse)
async def test_video(request: Request):
    """
    Простая тестовая страница для видеозвонков
    """
    with open("test_video.html", "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # Принимаем соединения с любого IP
        port=8000,
        log_level="info",
        reload=True
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True
    )