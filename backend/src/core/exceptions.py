from typing import Any, Dict, Optional
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback
import logging

from src.core.config_log import logger


class UserAPIException(Exception):
    """Базовый класс для всех пользовательских исключений."""
    
    def __init__(
        self, 
        message: str, 
        status_code: int = 500, 
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.user_message = user_message or message
        super().__init__(self.message)


class ValidationError(UserAPIException):
    """Ошибка валидации данных."""
    
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=400,
            details={"field": field} if field else {},
            user_message=f"Ошибка валидации: {message}"
        )


class AuthenticationError(UserAPIException):
    """Ошибка аутентификации."""
    
    def __init__(self, message: str = "Ошибка аутентификации"):
        super().__init__(
            message=message,
            status_code=401,
            user_message="Необходима авторизация"
        )


class AuthorizationError(UserAPIException):
    """Ошибка авторизации."""
    
    def __init__(self, message: str = "Недостаточно прав"):
        super().__init__(
            message=message,
            status_code=403,
            user_message="Доступ запрещен"
        )


class NotFoundError(UserAPIException):
    """Ресурс не найден."""
    
    def __init__(self, resource: str = "Ресурс"):
        super().__init__(
            message=f"{resource} не найден",
            status_code=404,
            user_message=f"{resource} не найден"
        )


class ConflictError(UserAPIException):
    """Конфликт данных."""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=409,
            user_message=message
        )


class RateLimitError(UserAPIException):
    """Превышен лимит запросов."""
    
    def __init__(self, message: str = "Слишком много запросов"):
        super().__init__(
            message=message,
            status_code=429,
            user_message="Слишком много запросов, попробуйте позже"
        )


class InternalServerError(UserAPIException):
    """Внутренняя ошибка сервера."""
    
    def __init__(self, message: str = "Внутренняя ошибка сервера"):
        super().__init__(
            message=message,
            status_code=500,
            user_message="Произошла внутренняя ошибка"
        )


def create_error_response(
    status_code: int,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None
) -> JSONResponse:
    """Создает стандартизированный ответ об ошибке."""
    
    error_response = {
        "error": {
            "code": status_code,
            "message": message,
            "timestamp": logger.get_timestamp() if hasattr(logger, 'get_timestamp') else None,
        }
    }
    
    if details:
        error_response["error"]["details"] = details
        
    if request_id:
        error_response["error"]["request_id"] = request_id
    
    return JSONResponse(
        status_code=status_code,
        content=error_response,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-cache"
        }
    )


async def user_api_exception_handler(request: Request, exc: UserAPIException) -> JSONResponse:
    """Обработчик для пользовательских исключений."""
    
    # Логируем ошибку с контекстом
    logger.error(
        f"UserAPI Exception: {exc.message} | "
        f"Path: {request.url.path} | "
        f"Method: {request.method} | "
        f"IP: {request.client.host if request.client else 'unknown'} | "
        f"Details: {exc.details}"
    )
    
    return create_error_response(
        status_code=exc.status_code,
        message=exc.user_message,
        details=exc.details
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Обработчик для HTTP исключений."""
    
    # Определяем пользовательское сообщение
    user_messages = {
        400: "Неверный запрос",
        401: "Необходима авторизация", 
        403: "Доступ запрещен",
        404: "Ресурс не найден",
        405: "Метод не разрешен",
        409: "Конфликт данных",
        422: "Ошибка валидации",
        429: "Слишком много запросов",
        500: "Внутренняя ошибка сервера",
        502: "Ошибка шлюза",
        503: "Сервис недоступен"
    }
    
    user_message = user_messages.get(exc.status_code, "Произошла ошибка")
    
    logger.warning(
        f"HTTP Exception: {exc.detail} | "
        f"Path: {request.url.path} | "
        f"Method: {request.method} | "
        f"IP: {request.client.host if request.client else 'unknown'}"
    )
    
    return create_error_response(
        status_code=exc.status_code,
        message=user_message,
        details={"original_detail": str(exc.detail)} if exc.detail else None
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Обработчик для ошибок валидации."""
    
    # Формируем детали ошибок валидации
    validation_details = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        validation_details.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning(
        f"Validation Error: {len(validation_details)} errors | "
        f"Path: {request.url.path} | "
        f"Method: {request.method} | "
        f"IP: {request.client.host if request.client else 'unknown'}"
    )
    
    return create_error_response(
        status_code=422,
        message="Ошибка валидации данных",
        details={"validation_errors": validation_details}
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обработчик для всех остальных исключений."""
    
    # Логируем полную информацию об ошибке
    logger.error(
        f"Unhandled Exception: {type(exc).__name__}: {str(exc)} | "
        f"Path: {request.url.path} | "
        f"Method: {request.method} | "
        f"IP: {request.client.host if request.client else 'unknown'} | "
        f"Traceback: {traceback.format_exc()}"
    )
    
    return create_error_response(
        status_code=500,
        message="Произошла внутренняя ошибка",
        details={"error_type": type(exc).__name__}
    )


def setup_exception_handlers(app):
    """Настраивает обработчики исключений для приложения."""
    
    # Добавляем обработчики исключений
    app.add_exception_handler(UserAPIException, user_api_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
