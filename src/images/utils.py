import mimetypes
from pathlib import Path
from typing import Set, Tuple, Dict
import uuid
import aiofiles
from fastapi import HTTPException, Response, UploadFile

from src.core.config_log import logger
from src.core.config_app import settings
from src.cache.redis_cache import get_bytes, set_bytes


ALLOWED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_MIME_TYPES: Set[str] = {
    "image/jpeg", 
    "image/jpg", 
    "image/png", 
    "image/gif", 
    "image/webp"
}
MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5 МБ
IMAGE_CACHE_TTL = settings.IMAGE_CACHE_TTL
IMAGE_CACHE_MAX_BYTES = settings.IMAGE_CACHE_MAX_BYTES

# Магические байты для проверки типов файлов
FILE_SIGNATURES: Dict[str, bytes] = {
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
    "gif": b"GIF87a" or b"GIF89a",
    "webp": b"RIFF"
}

def log_and_raise(status_code: int, detail: str):
    logger.error(detail)
    raise HTTPException(status_code=status_code, detail=detail)

def validate_extension(file_name: str) -> str:
    """Проверяет расширение файла на безопасность."""
    if not file_name or not file_name.strip():
        log_and_raise(400, "Имя файла не может быть пустым")
    
    # Проверяем на потенциально опасные символы
    dangerous_chars = ['..', '/', '\\', '<', '>', ':', '"', '|', '?', '*']
    if any(char in file_name for char in dangerous_chars):
        log_and_raise(400, "Имя файла содержит недопустимые символы")
    
    ext = Path(file_name).suffix.lower()
    if not ext:
        log_and_raise(400, "Файл должен иметь расширение")
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        log_and_raise(400, f"Неподдерживаемый формат файла. Разрешено: {allowed}")
    return ext

def validate_file_content(content: bytes) -> str:
    """Проверяет содержимое файла по магическим байтам."""
    if len(content) < 4:
        log_and_raise(400, "Файл слишком мал для проверки")
    
    # Проверяем магические байты
    for file_type, signature in FILE_SIGNATURES.items():
        if content.startswith(signature):
            return file_type
    
    # Дополнительная проверка для GIF
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "gif"
    
    # Дополнительная проверка для WebP
    if content.startswith(b"RIFF") and b"WEBP" in content[:12]:
        return "webp"
    
    log_and_raise(400, "Неподдерживаемый формат файла или поврежденный файл")

def validate_mime_type(content_type: str) -> None:
    """Проверяет MIME тип файла."""
    if not content_type:
        log_and_raise(400, "Не удалось определить тип файла")
    
    if content_type.lower() not in ALLOWED_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_MIME_TYPES))
        log_and_raise(400, f"Неподдерживаемый MIME тип. Разрешено: {allowed}")

def validate_file_size(content: bytes):
    if len(content) > MAX_FILE_SIZE:
        log_and_raise(400, f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE // (1024 * 1024)} МБ")


def safe_resolve_path(base: Path, target: Path) -> Path:
    try:
        base_resolved = base.resolve()
        target_resolved = target.resolve()
    except Exception as e:
        log_and_raise(400, f"Ошибка при обработке пути: {e}")

    if not str(target_resolved).startswith(str(base_resolved)):
        log_and_raise(400, "Недействительный путь к файлу")

    return target_resolved

async def save_uploaded_file(
    file: UploadFile,
    entity_id: int,
    directory: str | Path,
    entity_type: str = "user"
) -> str:
    """
    Сохраняет загруженный файл с комплексной проверкой безопасности.
    Возвращает имя сохранённого файла (без пути).
    """
    logger.info(f"Начало сохранения файла: entity={entity_type}, id={entity_id}, name={file.filename}")

    # Проверяем входные параметры
    if not file or not file.filename:
        log_and_raise(400, "Файл не предоставлен")
    
    if entity_id <= 0:
        log_and_raise(400, "Неверный ID сущности")
    
    if not entity_type or not entity_type.strip():
        log_and_raise(400, "Тип сущности не может быть пустым")

    directory = Path(directory)
    
    # Проверяем расширение файла
    ext = validate_extension(file.filename)
    
    # Проверяем MIME тип
    validate_mime_type(file.content_type)

    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Ошибка чтения файла {file.filename}: {e}")
        log_and_raise(400, "Ошибка чтения загруженного файла")

    # Проверяем размер файла
    validate_file_size(content)
    
    # Проверяем содержимое файла по магическим байтам
    detected_type = validate_file_content(content)
    logger.debug(f"Обнаружен тип файла: {detected_type}")

    # Генерируем безопасное имя файла
    unique_name = f"{entity_type}-{entity_id}-{uuid.uuid4().hex}{ext}"
    file_path = directory / unique_name

    # Проверяем путь на безопасность
    try:
        safe_path = safe_resolve_path(directory, file_path)
    except Exception as e:
        log_and_raise(400, f"Небезопасный путь к файлу: {e}")

    try:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Директория готова: {directory}")
    except Exception as e:
        logger.error(f"Ошибка создания директории {directory}: {e}")
        log_and_raise(500, "Не удалось создать директорию")

    try:
        async with aiofiles.open(safe_path, "wb") as out_f:
            await out_f.write(content)
    except Exception as e:
        logger.error(f"Ошибка записи файла {safe_path}: {e}")
        log_and_raise(500, "Ошибка записи файла")

    if not safe_path.exists():
        log_and_raise(500, "Файл не найден после сохранения")

    logger.info(f"Файл сохранён: {safe_path}")
    return unique_name


def _guess_mime(file_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(file_path))
    return mime or "application/octet-stream"

async def _read_and_maybe_cache(
    cache_key: str,
    path: Path,
) -> Tuple[bytes, bool]:
    """
    Читает файл с диска, при небольшом размере сохраняет в redis.
    Возвращает (data, from_cache).
    """
    # Попробуем взять из кэша
    cached = await get_bytes(cache_key)
    if cached is not None:
        logger.debug(f"Image cache hit: {cache_key}")
        return cached, True
    # Читаем с диска
    try:
        async with aiofiles.open(path, "rb") as f:
            data = await f.read()
    except FileNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Ошибка чтения файла {path}: {e}")
        raise
    # Сохраняем в кэш при малых размерах
    if len(data) <= IMAGE_CACHE_MAX_BYTES:
        ok = await set_bytes(cache_key, data, IMAGE_CACHE_TTL)
        if ok:
            logger.debug(f"Image cached: {cache_key} size={len(data)}")
    return data, False

def _resolve_with_alternative(base_dir: Path, requested: Path) -> Path:
    """
    Безопасно резолвит путь и для jpeg/jpg пробует альтернативный суффикс.
    """
    target = safe_resolve_path(base_dir, requested)
    if target.exists() and target.is_file():
        return target
    # Попробуем альтернативное расширение для jpeg/jpg
    suf = target.suffix.lower()
    if suf in (".jpeg", ".jpg"):
        alt_suffix = ".jpg" if suf == ".jpeg" else ".jpeg"
        alt_path = target.with_suffix(alt_suffix)
        if alt_path.exists() and alt_path.is_file():
            return alt_path
    return target

async def _serve_file(base_dir: Path, file: str) -> Response:
    request_path = base_dir / file
    try:
        target_path = _resolve_with_alternative(base_dir, request_path)
    except Exception as e:
        logger.error(f"Ошибка резолва пути для {file}: {e}")
        return log_and_raise(400, "Неверный путь")

    if not target_path.exists() or not target_path.is_file():
        return log_and_raise(404, "Изображение не найдено")

    cache_key = f"image:bytes:{file}"
    try:
        data, _ = await _read_and_maybe_cache(cache_key, target_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {target_path}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")
    mime = _guess_mime(target_path)
    return Response(content=data, media_type=mime)
