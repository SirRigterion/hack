import secrets
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import base64

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

from src.core.config_log import logger


class EncryptionManager:
    """Менеджер шифрования для видеоконференций."""
    
    def __init__(self):
        self.room_keys: Dict[int, str] = {}  # room_id -> encryption_key
        self.participant_keys: Dict[str, Dict] = {}  # connection_id -> keys
    
    def generate_room_key(self, room_id: int) -> str:
        """Генерация ключа шифрования для комнаты."""
        if not CRYPTOGRAPHY_AVAILABLE:
            logger.warning("cryptography не установлен. Шифрование недоступно.")
            return secrets.token_urlsafe(32)
            
        try:
            # Генерируем случайный ключ
            key = secrets.token_urlsafe(32)
            self.room_keys[room_id] = key
            
            logger.info(f"Сгенерирован ключ шифрования для комнаты {room_id}")
            return key
            
        except Exception as e:
            logger.error(f"Ошибка генерации ключа комнаты: {e}")
            raise
    
    def get_room_key(self, room_id: int) -> Optional[str]:
        """Получение ключа шифрования комнаты."""
        return self.room_keys.get(room_id)
    
    def generate_participant_keypair(self, connection_id: str) -> Dict[str, str]:
        """Генерация пары ключей для участника."""
        try:
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
            
            # Сохраняем ключи
            self.participant_keys[connection_id] = {
                'private_key': private_pem.decode(),
                'public_key': public_pem.decode(),
                'created_at': datetime.now()
            }
            
            logger.info(f"Сгенерирована пара ключей для участника {connection_id}")
            
            return {
                'private_key': private_pem.decode(),
                'public_key': public_pem.decode()
            }
            
        except Exception as e:
            logger.error(f"Ошибка генерации пары ключей: {e}")
            raise
    
    def get_participant_public_key(self, connection_id: str) -> Optional[str]:
        """Получение публичного ключа участника."""
        if connection_id in self.participant_keys:
            return self.participant_keys[connection_id]['public_key']
        return None
    
    def encrypt_room_key(self, room_key: str, participant_public_key: str) -> str:
        """Шифрование ключа комнаты публичным ключом участника."""
        try:
            # Загружаем публичный ключ
            public_key = serialization.load_pem_public_key(
                participant_public_key.encode()
            )
            
            # Шифруем ключ комнаты
            encrypted_key = public_key.encrypt(
                room_key.encode(),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Кодируем в base64
            return base64.b64encode(encrypted_key).decode()
            
        except Exception as e:
            logger.error(f"Ошибка шифрования ключа комнаты: {e}")
            raise
    
    def decrypt_room_key(self, encrypted_key: str, connection_id: str) -> Optional[str]:
        """Расшифровка ключа комнаты."""
        try:
            if connection_id not in self.participant_keys:
                return None
            
            # Загружаем приватный ключ
            private_key = serialization.load_pem_private_key(
                self.participant_keys[connection_id]['private_key'].encode(),
                password=None
            )
            
            # Декодируем из base64
            encrypted_data = base64.b64decode(encrypted_key)
            
            # Расшифровываем ключ
            room_key = private_key.decrypt(
                encrypted_data,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            return room_key.decode()
            
        except Exception as e:
            logger.error(f"Ошибка расшифровки ключа комнаты: {e}")
            return None
    
    def encrypt_media_data(self, data: bytes, room_key: str) -> bytes:
        """Шифрование медиа данных."""
        try:
            # Создаем ключ из пароля
            salt = b'video_salt'  # В продакшене используйте случайную соль
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(room_key.encode()))
            
            # Шифруем данные
            f = Fernet(key)
            encrypted_data = f.encrypt(data)
            
            return encrypted_data
            
        except Exception as e:
            logger.error(f"Ошибка шифрования медиа данных: {e}")
            raise
    
    def decrypt_media_data(self, encrypted_data: bytes, room_key: str) -> bytes:
        """Расшифровка медиа данных."""
        try:
            # Создаем ключ из пароля
            salt = b'video_salt'  # В продакшене используйте ту же соль
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(room_key.encode()))
            
            # Расшифровываем данные
            f = Fernet(key)
            decrypted_data = f.decrypt(encrypted_data)
            
            return decrypted_data
            
        except Exception as e:
            logger.error(f"Ошибка расшифровки медиа данных: {e}")
            raise
    
    def encrypt_signaling_data(self, data: Dict, room_key: str) -> str:
        """Шифрование сигнальных данных."""
        try:
            # Конвертируем данные в JSON
            json_data = json.dumps(data)
            
            # Шифруем данные
            encrypted_data = self.encrypt_media_data(json_data.encode(), room_key)
            
            # Кодируем в base64
            return base64.b64encode(encrypted_data).decode()
            
        except Exception as e:
            logger.error(f"Ошибка шифрования сигнальных данных: {e}")
            raise
    
    def decrypt_signaling_data(self, encrypted_data: str, room_key: str) -> Dict:
        """Расшифровка сигнальных данных."""
        try:
            # Декодируем из base64
            encrypted_bytes = base64.b64decode(encrypted_data)
            
            # Расшифровываем данные
            decrypted_data = self.decrypt_media_data(encrypted_bytes, room_key)
            
            # Конвертируем из JSON
            return json.loads(decrypted_data.decode())
            
        except Exception as e:
            logger.error(f"Ошибка расшифровки сигнальных данных: {e}")
            raise
    
    def generate_session_token(self, room_id: int, participant_id: int) -> str:
        """Генерация токена сессии."""
        try:
            # Создаем данные токена
            token_data = {
                'room_id': room_id,
                'participant_id': participant_id,
                'timestamp': datetime.now().isoformat(),
                'nonce': secrets.token_urlsafe(16)
            }
            
            # Конвертируем в JSON
            json_data = json.dumps(token_data)
            
            # Создаем хеш
            hash_obj = hashlib.sha256()
            hash_obj.update(json_data.encode())
            token_hash = hash_obj.hexdigest()
            
            # Кодируем токен
            token = base64.b64encode(f"{json_data}:{token_hash}".encode()).decode()
            
            logger.info(f"Сгенерирован токен сессии для участника {participant_id}")
            return token
            
        except Exception as e:
            logger.error(f"Ошибка генерации токена сессии: {e}")
            raise
    
    def validate_session_token(self, token: str, room_id: int) -> Optional[int]:
        """Валидация токена сессии."""
        try:
            # Декодируем токен
            decoded_token = base64.b64decode(token).decode()
            
            # Разделяем данные и хеш
            json_data, token_hash = decoded_token.split(':', 1)
            
            # Проверяем хеш
            hash_obj = hashlib.sha256()
            hash_obj.update(json_data.encode())
            expected_hash = hash_obj.hexdigest()
            
            if token_hash != expected_hash:
                return None
            
            # Парсим данные
            token_data = json.loads(json_data)
            
            # Проверяем комнату
            if token_data['room_id'] != room_id:
                return None
            
            # Проверяем время (токен действителен 24 часа)
            token_time = datetime.fromisoformat(token_data['timestamp'])
            if datetime.now() - token_time > timedelta(hours=24):
                return None
            
            return token_data['participant_id']
            
        except Exception as e:
            logger.error(f"Ошибка валидации токена сессии: {e}")
            return None
    
    def cleanup_expired_keys(self):
        """Очистка просроченных ключей."""
        try:
            current_time = datetime.now()
            expired_connections = []
            
            for connection_id, key_data in self.participant_keys.items():
                if 'created_at' in key_data:
                    key_age = current_time - key_data['created_at']
                    if key_age > timedelta(hours=24):  # Ключи действительны 24 часа
                        expired_connections.append(connection_id)
            
            # Удаляем просроченные ключи
            for connection_id in expired_connections:
                del self.participant_keys[connection_id]
                logger.info(f"Удален просроченный ключ для соединения {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки просроченных ключей: {e}")


class KeyExchangeManager:
    """Менеджер обмена ключами между участниками."""
    
    def __init__(self, encryption_manager: EncryptionManager):
        self.encryption_manager = encryption_manager
        self.pending_exchanges: Dict[str, Dict] = {}
    
    async def initiate_key_exchange(self, room_id: int, initiator_id: str, target_id: str) -> Dict:
        """Инициация обмена ключами."""
        try:
            # Получаем ключи участников
            initiator_public_key = self.encryption_manager.get_participant_public_key(initiator_id)
            target_public_key = self.encryption_manager.get_participant_public_key(target_id)
            
            if not initiator_public_key or not target_public_key:
                raise ValueError("Не найдены публичные ключи участников")
            
            # Создаем запрос обмена
            exchange_id = secrets.token_urlsafe(16)
            exchange_data = {
                'exchange_id': exchange_id,
                'room_id': room_id,
                'initiator_id': initiator_id,
                'target_id': target_id,
                'initiator_public_key': initiator_public_key,
                'created_at': datetime.now().isoformat()
            }
            
            # Сохраняем запрос
            self.pending_exchanges[exchange_id] = exchange_data
            
            logger.info(f"Инициирован обмен ключами между {initiator_id} и {target_id}")
            
            return {
                'exchange_id': exchange_id,
                'initiator_public_key': initiator_public_key
            }
            
        except Exception as e:
            logger.error(f"Ошибка инициации обмена ключами: {e}")
            raise
    
    async def complete_key_exchange(self, exchange_id: str, target_public_key: str) -> Dict:
        """Завершение обмена ключами."""
        try:
            if exchange_id not in self.pending_exchanges:
                raise ValueError("Запрос обмена ключами не найден")
            
            exchange_data = self.pending_exchanges[exchange_id]
            
            # Создаем финальные данные обмена
            final_data = {
                'exchange_id': exchange_id,
                'room_id': exchange_data['room_id'],
                'initiator_id': exchange_data['initiator_id'],
                'target_id': exchange_data['target_id'],
                'initiator_public_key': exchange_data['initiator_public_key'],
                'target_public_key': target_public_key,
                'completed_at': datetime.now().isoformat()
            }
            
            # Удаляем из ожидающих
            del self.pending_exchanges[exchange_id]
            
            logger.info(f"Завершен обмен ключами {exchange_id}")
            
            return final_data
            
        except Exception as e:
            logger.error(f"Ошибка завершения обмена ключами: {e}")
            raise
    
    async def get_pending_exchanges(self, participant_id: str) -> List[Dict]:
        """Получение ожидающих обменов ключами для участника."""
        pending = []
        
        for exchange_data in self.pending_exchanges.values():
            if exchange_data['target_id'] == participant_id:
                pending.append({
                    'exchange_id': exchange_data['exchange_id'],
                    'initiator_id': exchange_data['initiator_id'],
                    'initiator_public_key': exchange_data['initiator_public_key']
                })
        
        return pending


class SecureSignaling:
    """Безопасная передача сигналов WebRTC."""
    
    def __init__(self, encryption_manager: EncryptionManager):
        self.encryption_manager = encryption_manager
    
    def encrypt_offer(self, offer: Dict, room_key: str) -> str:
        """Шифрование WebRTC offer."""
        try:
            return self.encryption_manager.encrypt_signaling_data(offer, room_key)
        except Exception as e:
            logger.error(f"Ошибка шифрования offer: {e}")
            raise
    
    def decrypt_offer(self, encrypted_offer: str, room_key: str) -> Dict:
        """Расшифровка WebRTC offer."""
        try:
            return self.encryption_manager.decrypt_signaling_data(encrypted_offer, room_key)
        except Exception as e:
            logger.error(f"Ошибка расшифровки offer: {e}")
            raise
    
    def encrypt_answer(self, answer: Dict, room_key: str) -> str:
        """Шифрование WebRTC answer."""
        try:
            return self.encryption_manager.encrypt_signaling_data(answer, room_key)
        except Exception as e:
            logger.error(f"Ошибка шифрования answer: {e}")
            raise
    
    def decrypt_answer(self, encrypted_answer: str, room_key: str) -> Dict:
        """Расшифровка WebRTC answer."""
        try:
            return self.encryption_manager.decrypt_signaling_data(encrypted_answer, room_key)
        except Exception as e:
            logger.error(f"Ошибка расшифровки answer: {e}")
            raise
    
    def encrypt_ice_candidate(self, candidate: Dict, room_key: str) -> str:
        """Шифрование ICE кандидата."""
        try:
            return self.encryption_manager.encrypt_signaling_data(candidate, room_key)
        except Exception as e:
            logger.error(f"Ошибка шифрования ICE кандидата: {e}")
            raise
    
    def decrypt_ice_candidate(self, encrypted_candidate: str, room_key: str) -> Dict:
        """Расшифровка ICE кандидата."""
        try:
            return self.encryption_manager.decrypt_signaling_data(encrypted_candidate, room_key)
        except Exception as e:
            logger.error(f"Ошибка расшифровки ICE кандидата: {e}")
            raise


# Глобальные экземпляры
encryption_manager = EncryptionManager()
key_exchange_manager = KeyExchangeManager(encryption_manager)
secure_signaling = SecureSignaling(encryption_manager)
