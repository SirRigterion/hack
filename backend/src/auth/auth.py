from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from jose import JWTError, jwt
from fastapi import HTTPException, Depends, Request, Response
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User
from src.core.config_log import logger
from src.core.config_app import settings


def create_access_token(
    *, 
    subject: str, 
    roles: list[str], 
    expires_delta: timedelta | None = None) -> str:
    """Создаёт JWT токен с ограниченным временем жизни и дополнительными проверками безопасности."""
    
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_SECONDS))
    
    # Проверяем, что subject является числом (user_id)
    try:
        user_id = int(subject)
    except (ValueError, TypeError):
        raise ValueError("Subject должен быть числовым ID пользователя")
    
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "roles": roles,
        "iat": now,
        "exp": expire,
        "token_type": "bearer",
        "iss": settings.PROJECT_NAME, 
        "aud": "user-api"
    }
    
    if not settings.SECRET_KEY:
        raise ValueError("SECRET_KEY не установлен")
        
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True, # True = frontend Не достанит 
        secure=settings.COOKIE_MODE, # 1 - http не передаст (только https) 0 - http передаст
        samesite="lax",                    # или 'strict' для более жёсткой политики
        max_age=settings.ACCESS_TOKEN_EXPIRE_SECONDS * 60,
        expires=settings.ACCESS_TOKEN_EXPIRE_SECONDS * 60,
        #domain=domain
    )


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Извлекает текущего пользователя из токена в куки с улучшенной валидацией."""
    credentials_exception = HTTPException(
        status_code=401,
        detail="Не удалось проверить учетные данные",
        headers={"WWW-Authenticate": "Bearer"}
    )
    
    token = request.cookies.get("access_token")
    if not token:
        logger.warning(f"Отсутствует токен доступа, IP: {request.client.host if request.client else 'unknown'}")
        raise credentials_exception
    
    try:
        # Декодируем токен с дополнительными проверками
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM],
            audience="user-api",
            issuer=settings.PROJECT_NAME
        )
        
        # Проверяем обязательные поля
        user_id_str = payload.get("sub")
        token_type = payload.get("token_type")
        
        if not user_id_str:
            logger.warning("Отсутствует subject в токене")
            raise credentials_exception
            
        if token_type != "bearer":
            logger.warning(f"Неверный тип токена: {token_type}")
            raise credentials_exception
        
        # Проверяем формат user_id
        try:
            user_id = int(user_id_str)
            if user_id <= 0:
                raise ValueError("ID пользователя должен быть положительным числом")
        except (ValueError, TypeError):
            logger.warning(f"Неверный формат user_id в токене: {user_id_str}")
            raise credentials_exception
        
        # Получаем пользователя из БД
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"Пользователь с ID {user_id} не найден в БД")
            raise credentials_exception
            
        # Проверяем статус пользователя
        if user.is_deleted:
            logger.warning(f"Попытка доступа удаленного пользователя ID {user_id}")
            raise HTTPException(status_code=403, detail="Аккаунт удален")
            
        return user
        
    except JWTError as e:
        logger.warning(f"Ошибка декодирования JWT токена: {e}")
        raise credentials_exception
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при проверке токена: {e}")
        raise credentials_exception