from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException
import re

from src.auth.auth import get_current_user
from src.db.models import User
from src.core.config_app import settings
from src.core.config_log import logger
from src.images.utils import _serve_file
from src.utils.decorators import require_cookie_and_not_deleted


router = APIRouter(prefix="/images", tags=["images"])

def validate_file_path(file_path: str) -> bool:
    """Проверяет безопасность пути к файлу."""
    # Проверяем на path traversal атаки
    if '..' in file_path or file_path.startswith('/'):
        return False
    
    # Проверяем на опасные символы
    dangerous_patterns = [r'[<>:"|?*]', r'\.\.', r'^/', r'\\']
    for pattern in dangerous_patterns:
        if re.search(pattern, file_path):
            return False
    
    # Проверяем длину пути
    if len(file_path) > 255:
        return False
        
    return True

@router.get("/public/{file:path}")
async def public_image(
    file: str,
):
    """Безопасный доступ к публичным изображениям."""
    logger.info(f"Публичный запрос изображения: {file}")
    
    # Проверяем безопасность пути
    if not validate_file_path(file):
        logger.warning(f"Попытка небезопасного доступа к файлу: {file}")
        raise HTTPException(status_code=400, detail="Неверный путь к файлу")
    
    # Дополнительная проверка расширения
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
    file_ext = Path(file).suffix.lower()
    if file_ext not in allowed_extensions:
        logger.warning(f"Попытка доступа к файлу с неразрешенным расширением: {file}")
        raise HTTPException(status_code=400, detail="Неподдерживаемый тип файла")
    
    return await _serve_file(Path(settings.UPLOAD_DIR), file)


@router.get("/private/{file:path}")
@require_cookie_and_not_deleted
async def private_image(
    file: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Безопасный доступ к приватным изображениям (аватарам)."""
    logger.info(f"Приватный запрос изображения (аватар): {file}")
    
    # Проверяем безопасность пути
    if not validate_file_path(file):
        logger.warning(f"Попытка небезопасного доступа к приватному файлу: {file}, user_id: {current_user.user_id}")
        raise HTTPException(status_code=400, detail="Неверный путь к файлу")
    
    # Дополнительная проверка расширения
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    file_ext = Path(file).suffix.lower()
    if file_ext not in allowed_extensions:
        logger.warning(f"Попытка доступа к приватному файлу с неразрешенным расширением: {file}, user_id: {current_user.user_id}")
        raise HTTPException(status_code=400, detail="Неподдерживаемый тип файла")
    
    # Проверяем, что пользователь имеет доступ к этому файлу
    # Файлы аватаров должны содержать user_id в имени
    is_user_file = file.startswith(f"user-{current_user.user_id}-")
    
    
    if not is_user_file:
        logger.warning(f"Попытка доступа к чужому аватару: {file}, user_id: {current_user.user_id}")
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    return await _serve_file(Path(settings.AVATAR_DIR), file)