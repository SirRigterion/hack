"""
Система шифрования для видео комнат
"""
import secrets
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from typing import Optional, Dict, Any
from src.core.config_log import logger


class RoomEncryption:
    """Класс для управления шифрованием комнат"""
    
    def __init__(self):
        self.room_keys: Dict[str, bytes] = {}
    
    def generate_room_key(self, room_code: str) -> str:
        """Генерация ключа шифрования для комнаты"""
        try:
            # Генерируем случайную соль
            salt = secrets.token_bytes(16)
            
            # Создаем ключ на основе кода комнаты и соли
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            # Используем код комнаты как пароль
            key = base64.urlsafe_b64encode(kdf.derive(room_code.encode()))
            
            # Сохраняем ключ для комнаты
            self.room_keys[room_code] = key
            
            logger.info(f"Сгенерирован ключ шифрования для комнаты {room_code}")
            return key.decode()
            
        except Exception as e:
            logger.error(f"Ошибка генерации ключа для комнаты {room_code}: {e}")
            raise
    
    def get_room_key(self, room_code: str) -> Optional[bytes]:
        """Получение ключа шифрования комнаты"""
        return self.room_keys.get(room_code)
    
    def encrypt_data(self, data: str, room_code: str) -> str:
        """Шифрование данных для комнаты"""
        try:
            key = self.get_room_key(room_code)
            if not key:
                # Генерируем ключ если его нет
                self.generate_room_key(room_code)
                key = self.get_room_key(room_code)
            
            fernet = Fernet(key)
            encrypted_data = fernet.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
            
        except Exception as e:
            logger.error(f"Ошибка шифрования данных для комнаты {room_code}: {e}")
            raise
    
    def decrypt_data(self, encrypted_data: str, room_code: str) -> str:
        """Расшифровка данных для комнаты"""
        try:
            key = self.get_room_key(room_code)
            if not key:
                raise ValueError(f"Ключ для комнаты {room_code} не найден")
            
            fernet = Fernet(key)
            decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = fernet.decrypt(decoded_data)
            return decrypted_data.decode()
            
        except Exception as e:
            logger.error(f"Ошибка расшифровки данных для комнаты {room_code}: {e}")
            raise
    
    def encrypt_webrtc_signal(self, signal_data: Dict[str, Any], room_code: str) -> Dict[str, Any]:
        """Шифрование WebRTC сигнала"""
        try:
            import json
            signal_json = json.dumps(signal_data)
            encrypted_signal = self.encrypt_data(signal_json, room_code)
            
            return {
                "encrypted": True,
                "data": encrypted_signal,
                "room_code": room_code
            }
            
        except Exception as e:
            logger.error(f"Ошибка шифрования WebRTC сигнала: {e}")
            return signal_data  # Возвращаем исходные данные в случае ошибки
    
    def decrypt_webrtc_signal(self, encrypted_signal: Dict[str, Any], room_code: str) -> Dict[str, Any]:
        """Расшифровка WebRTC сигнала"""
        try:
            if not encrypted_signal.get("encrypted"):
                return encrypted_signal
            
            decrypted_data = self.decrypt_data(encrypted_signal["data"], room_code)
            import json
            return json.loads(decrypted_data)
            
        except Exception as e:
            logger.error(f"Ошибка расшифровки WebRTC сигнала: {e}")
            return encrypted_signal  # Возвращаем исходные данные в случае ошибки
    
    def remove_room_key(self, room_code: str):
        """Удаление ключа комнаты"""
        if room_code in self.room_keys:
            del self.room_keys[room_code]
            logger.info(f"Удален ключ шифрования для комнаты {room_code}")
    
    def get_room_key_hash(self, room_code: str) -> str:
        """Получение хеша ключа комнаты для проверки целостности"""
        try:
            key = self.get_room_key(room_code)
            if not key:
                return ""
            
            return hashlib.sha256(key).hexdigest()
            
        except Exception as e:
            logger.error(f"Ошибка получения хеша ключа для комнаты {room_code}: {e}")
            return ""


# Глобальный экземпляр системы шифрования
room_encryption = RoomEncryption()
