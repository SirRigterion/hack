import json
from typing import Dict, List, Optional
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
from sqlalchemy import select

from src.db.models import User
from src.core.config_app import settings
from src.core.config_log import logger


class UniversalConnectionManager:
    """
    Универсальный менеджер WebSocket соединений для чата и видео
    """

    def __init__(self):
        # Структура: {room_id: [{websocket, user_data, connection_type}]}
        self.active_connections: Dict[str, List[dict]] = {}
        # Отслеживание типов соединений: 'chat', 'video', 'both'
        self.connection_types: Dict[str, str] = {}

    async def authenticate_websocket(self, token: str, db: AsyncSession) -> Optional[dict]:
        """Аутентификация пользователя по JWT токену"""
        try:
            if not token:
                return None

            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                audience="user-api",
                issuer=settings.PROJECT_NAME
            )

            user_id_str = payload.get("sub")
            token_type = payload.get("token_type")

            if not user_id_str or token_type != "bearer":
                return None

            user_id = int(user_id_str)
            if user_id <= 0:
                return None

            # Получаем пользователя из БД
            result = await db.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()

            if not user or user.is_deleted:
                return None

            return {
                "user_id": user.user_id,
                "username": user.user_login,
                "full_name": user.user_full_name,
                "roles": [user.role_id],
                "avatar_url": user.user_avatar_url
            }

        except (JWTError, ValueError, TypeError) as e:
            logger.warning(f"WebSocket auth error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected WebSocket auth error: {e}")
            return None

    async def connect(self, websocket: WebSocket, room_id: str, user: dict, connection_type: str = "chat"):
        """Подключение пользователя к комнате"""
        await websocket.accept()

        if room_id not in self.active_connections:
            self.active_connections[room_id] = []

        connection_data = {
            "websocket": websocket,
            "user_id": user["user_id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "roles": user["roles"],
            "avatar_url": user.get("avatar_url"),
            "connection_type": connection_type
        }

        self.active_connections[room_id].append(connection_data)

        # Обновляем тип соединения для комнаты
        if room_id not in self.connection_types:
            self.connection_types[room_id] = connection_type
        elif self.connection_types[room_id] != connection_type:
            self.connection_types[room_id] = "both"  # Чат + видео

        logger.info(f"✅ {connection_type.upper()} WebSocket: {user['username']} -> {room_id}")

        # Уведомляем о новом участнике
        await self.broadcast_to_room(
            {
                "type": "user_joined",
                "user_id": user["user_id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "connection_type": connection_type,
                "participants_count": len(self.active_connections[room_id]),
                "timestamp": self._get_timestamp()
            },
            room_id,
            exclude_user_id=user["user_id"]
        )

    def disconnect(self, websocket: WebSocket, room_id: str) -> Optional[dict]:
        """Отключение пользователя от комнаты"""
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                if connection["websocket"] == websocket:
                    disconnected_user = connection
                    self.active_connections[room_id].remove(connection)

                    # Если комната пустая, очищаем
                    if not self.active_connections[room_id]:
                        del self.active_connections[room_id]
                        if room_id in self.connection_types:
                            del self.connection_types[room_id]

                    logger.info(f"❌ WebSocket: {disconnected_user['username']} отключился от {room_id}")
                    return disconnected_user
        return None

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Отправка личного сообщения"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Ошибка отправки личного сообщения: {e}")
            raise

    async def broadcast_to_room(self, message: dict, room_id: str, exclude_user_id: int = None):
        """Широковещательная отправка в комнату с отладкой"""
        print(f"🔊 BROADCAST to room {room_id}: {message['type']}")
        print(f"   Active connections in room: {len(self.active_connections.get(room_id, []))}")

        if room_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[room_id]:
                if connection["user_id"] != exclude_user_id:
                    try:
                        print(f"   → Sending to user {connection['username']} (ID: {connection['user_id']})")
                        await connection["websocket"].send_json(message)
                    except Exception as e:
                        print(f"   ❌ Error sending to {connection['username']}: {e}")
                        disconnected.append(connection)

            # Удаляем отключенные соединения
            for connection in disconnected:
                self.disconnect(connection["websocket"], room_id)
        else:
            print(f"   ❌ Room {room_id} not found in active connections")

    async def send_to_user(self, message: dict, room_id: str, user_id: int):
        """Отправка сообщения конкретному пользователю"""
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
        """Получение списка участников комнаты"""
        if room_id in self.active_connections:
            return [
                {
                    "user_id": conn["user_id"],
                    "username": conn["username"],
                    "full_name": conn["full_name"],
                    "avatar_url": conn["avatar_url"],
                    "connection_type": conn["connection_type"]
                }
                for conn in self.active_connections[room_id]
            ]
        return []

    def _get_timestamp(self):
        from datetime import datetime
        return datetime.now().isoformat()


# Глобальные экземпляры менеджеров
chat_manager = UniversalConnectionManager()
video_manager = UniversalConnectionManager()

# Универсальный менеджер для обратной совместимости
manager = UniversalConnectionManager()
