from typing import Dict, List, Optional
from fastapi import WebSocket, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import User

from src.core.config_app import settings
from src.core.config_log import logger


class ConnectionManager:
    def __init__(self):
        # room_id -> list of {websocket, user_id, username}
        self.active_connections: Dict[str, List[dict]] = {}

    async def authenticate_websocket(self, token: str, db: AsyncSession) -> Optional[dict]:
        """Аутентификация пользователя по JWT токену (как в auth.py)"""
        credentials_exception = None

        try:
            if not token:
                return None

            # Декодируем токен (как в get_current_user)
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
                logger.warning("Отсутствует subject в токене WebSocket")
                return None

            if token_type != "bearer":
                logger.warning(f"Неверный тип токена WebSocket: {token_type}")
                return None

            # Проверяем формат user_id
            try:
                user_id = int(user_id_str)
                if user_id <= 0:
                    return None
            except (ValueError, TypeError):
                logger.warning(f"Неверный формат user_id в токене WebSocket: {user_id_str}")
                return None

            # Получаем пользователя из БД
            result = await db.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь с ID {user_id} не найден в БД для WebSocket")
                return None

            # Проверяем статус пользователя
            if user.is_deleted:
                logger.warning(f"Попытка доступа удаленного пользователя ID {user_id} к WebSocket")
                return None

            return {
                "user_id": user.user_id,
                "username": user.user_login,
                "full_name": user.user_full_name,
                "roles": [user.role_id]
            }

        except JWTError as e:
            logger.warning(f"Ошибка декодирования JWT токена WebSocket: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при проверке токена WebSocket: {e}")
            return None

    async def connect(self, websocket: WebSocket, room_id: str, user: dict):
        await websocket.accept()

        if room_id not in self.active_connections:
            self.active_connections[room_id] = []

        connection_data = {
            "websocket": websocket,
            "user_id": user["user_id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "roles": user["roles"]
        }

        self.active_connections[room_id].append(connection_data)

        logger.info(
            f"✅ WebSocket: {user['username']} подключился к комнате {room_id}. Всего: {len(self.active_connections[room_id])}")

        # Уведомляем других участников о новом пользователе
        await self.broadcast_to_room(
            {
                "type": "user_joined",
                "user_id": user["user_id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "message": f"{user['full_name']} присоединился к конференции",
                "participants_count": len(self.active_connections[room_id]),
                "timestamp": self._get_timestamp()
            },
            room_id,
            exclude_user_id=user["user_id"]
        )

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            disconnected_user = None
            for connection in self.active_connections[room_id]:
                if connection["websocket"] == websocket:
                    disconnected_user = connection
                    self.active_connections[room_id].remove(connection)
                    break

            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

            if disconnected_user:
                logger.info(f"❌ WebSocket: {disconnected_user['username']} отключился от комнаты {room_id}")
                return disconnected_user

        return None

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Ошибка отправки личного сообщения: {e}")

    async def broadcast_to_room(self, message: dict, room_id: str, exclude_user_id: int = None):
        """Отправка сообщения всем в комнате, кроме указанного пользователя"""
        if room_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[room_id]:
                if connection["user_id"] != exclude_user_id:
                    try:
                        await connection["websocket"].send_json(message)
                    except Exception as e:
                        logger.error(f"Ошибка отправки пользователю {connection['username']}: {e}")
                        disconnected.append(connection["websocket"])

            # Удаляем отключенные соединения
            for websocket in disconnected:
                self.disconnect(websocket, room_id)

    async def send_to_user(self, message: dict, room_id: str, user_id: int):
        """Отправка сообщения конкретному пользователю в комнате"""
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                if connection["user_id"] == user_id:
                    try:
                        await connection["websocket"].send_json(message)
                        return True
                    except Exception as e:
                        logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
                        self.disconnect(connection["websocket"], room_id)
        return False

    def get_room_participants(self, room_id: str) -> List[dict]:
        """Получить список участников комнаты"""
        if room_id in self.active_connections:
            return [
                {
                    "user_id": conn["user_id"],
                    "username": conn["username"],
                    "full_name": conn["full_name"],
                    "roles": conn["roles"]
                }
                for conn in self.active_connections[room_id]
            ]
        return []

    def _get_timestamp(self):
        from datetime import datetime
        return datetime.now().isoformat()


manager = ConnectionManager()