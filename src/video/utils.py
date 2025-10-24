import secrets
import string
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

# Импорты с проверкой доступности
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.fernet import Fernet
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    import numpy as np

from src.core.config_app import settings
from src.core.config_log import logger


class RoomCodeGenerator:
    """Генератор уникальных кодов для комнат."""
    
    @staticmethod
    def generate_room_code(length: int = 8) -> str:
        """Генерация уникального кода комнаты."""
        # Используем буквы и цифры, исключая похожие символы
        alphabet = string.ascii_uppercase + string.digits
        # Исключаем похожие символы
        alphabet = alphabet.replace('0', '').replace('O', '').replace('I', '').replace('1', '')
        
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_invitation_code(length: int = 12) -> str:
        """Генерация кода приглашения."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))


class RoomURLGenerator:
    """Генератор URL для комнат."""
    
    @staticmethod
    def generate_room_url(room_code: str, base_url: Optional[str] = None) -> str:
        """Генерация URL для комнаты."""
        if base_url is None:
            base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        
        return urljoin(base_url, f"/video/room/{room_code}")
    
    @staticmethod
    def generate_invitation_url(invitation_code: str, base_url: Optional[str] = None) -> str:
        """Генерация URL для приглашения."""
        if base_url is None:
            base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        
        return urljoin(base_url, f"/video/invite/{invitation_code}")


class EncryptionManager:
    """Менеджер шифрования для комнат."""
    
    @staticmethod
    def generate_encryption_key() -> str:
        """Генерация ключа шифрования для комнаты."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def generate_key_pair():
        """Генерация пары ключей для участника."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography не установлен. Установите: pip install cryptography")
            
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        
        # Генерируем приватный ключ
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Получаем публичный ключ
        public_key = private_key.public_key()
        
        # Сериализуем ключи
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return {
            'private_key': private_pem.decode(),
            'public_key': public_pem.decode()
        }
    
    @staticmethod
    def encrypt_data(data: str, key: str) -> str:
        """Шифрование данных."""
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import base64
        
        # Создаем ключ из пароля
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'salt',  # В продакшене используйте случайную соль
            iterations=100000,
        )
        key_bytes = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        
        # Шифруем данные
        f = Fernet(key_bytes)
        encrypted_data = f.encrypt(data.encode())
        
        return base64.urlsafe_b64encode(encrypted_data).decode()
    
    @staticmethod
    def decrypt_data(encrypted_data: str, key: str) -> str:
        """Расшифровка данных."""
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import base64
        
        # Создаем ключ из пароля
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'salt',  # В продакшене используйте ту же соль
            iterations=100000,
        )
        key_bytes = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        
        # Расшифровываем данные
        f = Fernet(key_bytes)
        decrypted_data = f.decrypt(base64.urlsafe_b64decode(encrypted_data))
        
        return decrypted_data.decode()


class MediaQualityManager:
    """Менеджер качества медиа."""
    
    QUALITY_SETTINGS = {
        'low': {
            'video': {'width': 320, 'height': 240, 'bitrate': 300},
            'audio': {'bitrate': 64}
        },
        'medium': {
            'video': {'width': 640, 'height': 480, 'bitrate': 800},
            'audio': {'bitrate': 128}
        },
        'high': {
            'video': {'width': 1280, 'height': 720, 'bitrate': 2000},
            'audio': {'bitrate': 256}
        },
        'auto': {
            'video': {'width': 1280, 'height': 720, 'bitrate': 1500},
            'audio': {'bitrate': 128}
        }
    }
    
    @staticmethod
    def get_quality_settings(quality: str) -> dict:
        """Получение настроек качества."""
        return MediaQualityManager.QUALITY_SETTINGS.get(quality, MediaQualityManager.QUALITY_SETTINGS['auto'])
    
    @staticmethod
    def adjust_quality_for_bandwidth(quality: str, bandwidth: int) -> str:
        """Автоматическая настройка качества в зависимости от пропускной способности."""
        if bandwidth < 500:  # kbps
            return 'low'
        elif bandwidth < 1500:
            return 'medium'
        else:
            return 'high'


class RoomValidator:
    """Валидатор комнат."""
    
    @staticmethod
    def validate_room_name(name: str) -> bool:
        """Валидация названия комнаты."""
        if not name or len(name.strip()) < 1:
            return False
        if len(name) > 100:
            return False
        # Проверяем на запрещенные символы
        forbidden_chars = ['<', '>', '"', "'", '&', '\n', '\r', '\t']
        return not any(char in name for char in forbidden_chars)
    
    @staticmethod
    def validate_room_code(code: str) -> bool:
        """Валидация кода комнаты."""
        if not code or len(code) < 4:
            return False
        if len(code) > 20:
            return False
        # Проверяем, что код содержит только допустимые символы
        allowed_chars = string.ascii_uppercase + string.digits
        return all(char in allowed_chars for char in code)
    
    @staticmethod
    def validate_participant_limit(limit: int) -> bool:
        """Валидация лимита участников."""
        return 2 <= limit <= 1000


class FileManager:
    """Менеджер файлов для записей."""
    
    @staticmethod
    def generate_recording_filename(room_id: int, timestamp: datetime) -> str:
        """Генерация имени файла для записи."""
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"recording_room_{room_id}_{date_str}.mp4"
    
    @staticmethod
    def generate_thumbnail_filename(recording_id: int) -> str:
        """Генерация имени файла для превью."""
        return f"thumbnail_recording_{recording_id}.jpg"
    
    @staticmethod
    def get_file_size_mb(file_path: str) -> int:
        """Получение размера файла в МБ."""
        import os
        try:
            size_bytes = os.path.getsize(file_path)
            return size_bytes // (1024 * 1024)
        except OSError:
            return 0
    
    @staticmethod
    def get_recording_duration(file_path: str) -> int:
        """Получение длительности записи в секундах."""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV не установлен. Получение длительности недоступно.")
            return 0
            
        try:
            cap = cv2.VideoCapture(file_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            duration = int(frame_count / fps) if fps > 0 else 0
            cap.release()
            return duration
        except Exception as e:
            logger.error(f"Ошибка получения длительности записи: {e}")
            return 0


class EventLogger:
    """Логгер событий комнаты."""
    
    @staticmethod
    def log_room_event(
        room_id: int,
        event_type: str,
        participant_id: Optional[int] = None,
        event_data: Optional[dict] = None
    ):
        """Логирование события комнаты."""
        logger.info(
            f"Room Event - Room: {room_id}, "
            f"Event: {event_type}, "
            f"Participant: {participant_id}, "
            f"Data: {event_data}"
        )
    
    @staticmethod
    def log_participant_join(room_id: int, participant_id: int, user_id: int):
        """Логирование присоединения участника."""
        EventLogger.log_room_event(
            room_id=room_id,
            event_type="participant_join",
            participant_id=participant_id,
            event_data={"user_id": user_id}
        )
    
    @staticmethod
    def log_participant_leave(room_id: int, participant_id: int, user_id: int):
        """Логирование выхода участника."""
        EventLogger.log_room_event(
            room_id=room_id,
            event_type="participant_leave",
            participant_id=participant_id,
            event_data={"user_id": user_id}
        )
    
    @staticmethod
    def log_recording_start(room_id: int, started_by: int):
        """Логирование начала записи."""
        EventLogger.log_room_event(
            room_id=room_id,
            event_type="recording_start",
            event_data={"started_by": started_by}
        )
    
    @staticmethod
    def log_recording_stop(room_id: int, stopped_by: int):
        """Логирование остановки записи."""
        EventLogger.log_room_event(
            room_id=room_id,
            event_type="recording_stop",
            event_data={"stopped_by": stopped_by}
        )
