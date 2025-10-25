import uuid
from typing import Dict, Optional
from fastapi import WebSocket
from src.core.config_log import logger


class Room:
    def __init__(self, room_id: str, owner_id: int):
        self.room_id = room_id
        self.owner_id = owner_id
        self.participants: Dict[int, WebSocket] = {}
        self.is_active = True


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def create_room(self, owner_id: int) -> str:
        """Создать новую комнату"""
        room_id = str(uuid.uuid4())
        self.rooms[room_id] = Room(room_id, owner_id)
        logger.info(f"Создана комната {room_id} владельцем {owner_id}")
        return room_id

    def get_room(self, room_id: str) -> Optional[Room]:
        """Получить комнату по ID"""
        return self.rooms.get(room_id)

    async def connect_user(self, room_id: str, user_id: int, websocket: WebSocket):
        """Подключить пользователя к комнате"""
        room = self.get_room(room_id)
        if not room:
            raise ValueError(f"Комната {room_id} не найдена")

        room.participants[user_id] = websocket
        logger.info(f"Пользователь {user_id} подключен к комнате {room_id}")

        # Уведомляем других участников о новом пользователе
        await self.broadcast_to_room(
            room_id,
            {"type": "user_joined", "user_id": user_id},
            exclude_user=user_id
        )

    def disconnect_user(self, room_id: str, user_id: int):
        """Отключить пользователя от комнаты"""
        room = self.get_room(room_id)
        if room and user_id in room.participants:
            del room.participants[user_id]
            logger.info(f"Пользователь {user_id} отключен от комнаты {room_id}")

            # Если комната пустая, удаляем её
            if not room.participants:
                self.delete_room(room_id)

    async def broadcast_to_room(self, room_id: str, message: dict, exclude_user: Optional[int] = None):
        """Отправить сообщение всем участникам комнаты"""
        room = self.get_room(room_id)
        if not room:
            return

        for user_id, websocket in room.participants.items():
            if user_id == exclude_user:
                continue

            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
                # Удаляем отключенного пользователя
                self.disconnect_user(room_id, user_id)

    def delete_room(self, room_id: str):
        """Удалить комнату"""
        if room_id in self.rooms:
            del self.rooms[room_id]
            logger.info(f"Комната {room_id} удалена")

    def get_active_rooms(self) -> list:
        """Получить список активных комнат"""
        return [
            {
                "room_id": room.room_id,
                "owner_id": room.owner_id,
                "participant_count": len(room.participants)
            }
            for room in self.rooms.values() if room.is_active
        ]