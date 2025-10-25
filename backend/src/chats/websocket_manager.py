import json
import asyncio
from typing import Dict, Set, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from src.db.database import get_db
from src.db.models import  ChatParticipant
from src.chats.schemas import (
    ChatMessageWebSocket, 
    UserTypingWebSocket,
    UserOnlineWebSocket,
    MessageResponse
)
from src.core.config_log import logger


class ConnectionManager:
    """
    Менеджер WebSocket соединений для чата.
    """
    
    def __init__(self):
        # Активные соединения по user_id
        self.active_connections: Dict[int, WebSocket] = {}
        # Соединения по комнатам
        self.room_connections: Dict[int, Set[int]] = {}
        # Пользователи, которые печатают
        self.typing_users: Dict[int, Set[int]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: int):
        """Подключение пользователя к WebSocket."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        
        # Получаем комнаты пользователя
        async with get_db() as session:
            stmt = select(ChatParticipant.room_id).where(ChatParticipant.user_id == user_id)
            result = await session.execute(stmt)
            room_ids = result.scalars().all()
            
            for room_id in room_ids:
                if room_id not in self.room_connections:
                    self.room_connections[room_id] = set()
                self.room_connections[room_id].add(user_id)
        
        logger.info(f"Пользователь {user_id} подключился к WebSocket")
        
        # Уведомляем о том, что пользователь онлайн
        await self.broadcast_user_online(user_id, True)
    
    def disconnect(self, user_id: int):
        """Отключение пользователя от WebSocket."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        
        # Удаляем из всех комнат
        for room_id, users in self.room_connections.items():
            users.discard(user_id)
            if not users:
                del self.room_connections[room_id]
        
        # Удаляем из печатающих
        for room_id, typing_users in self.typing_users.items():
            typing_users.discard(user_id)
            if not typing_users:
                del self.typing_users[room_id]
        
        logger.info(f"Пользователь {user_id} отключился от WebSocket")
    
    async def send_personal_message(self, message: dict, user_id: int):
        """Отправка личного сообщения пользователю."""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
                self.disconnect(user_id)
    
    async def send_to_room(self, message: dict, room_id: int, exclude_user: Optional[int] = None):
        """Отправка сообщения всем участникам комнаты."""
        if room_id in self.room_connections:
            for user_id in self.room_connections[room_id]:
                if user_id != exclude_user:
                    await self.send_personal_message(message, user_id)
    
    async def broadcast_user_online(self, user_id: int, is_online: bool):
        """Уведомление о статусе пользователя."""
        # Получаем комнаты пользователя
        async with get_db() as session:
            stmt = select(ChatParticipant.room_id).where(ChatParticipant.user_id == user_id)
            result = await session.execute(stmt)
            room_ids = result.scalars().all()
            
            for room_id in room_ids:
                message = UserOnlineWebSocket(
                    type="user_online",
                    data={
                        "user_id": user_id,
                        "is_online": is_online,
                        "room_id": room_id
                    }
                ).dict()
                await self.send_to_room(message, room_id, exclude_user=user_id)
    
    async def broadcast_typing(self, user_id: int, room_id: int, is_typing: bool):
        """Уведомление о том, что пользователь печатает."""
        if is_typing:
            if room_id not in self.typing_users:
                self.typing_users[room_id] = set()
            self.typing_users[room_id].add(user_id)
        else:
            if room_id in self.typing_users:
                self.typing_users[room_id].discard(user_id)
                if not self.typing_users[room_id]:
                    del self.typing_users[room_id]
        
        message = UserTypingWebSocket(
            type="user_typing",
            data={
                "user_id": user_id,
                "room_id": room_id,
                "is_typing": is_typing,
                "typing_users": list(self.typing_users.get(room_id, set()))
            }
        ).dict()
        
        await self.send_to_room(message, room_id, exclude_user=user_id)
    
    async def broadcast_message(self, message_data: MessageResponse, room_id: int):
        """Отправка сообщения всем участникам комнаты."""
        message = ChatMessageWebSocket(
            type="chat_message",
            data=message_data
        ).dict()
        
        await self.send_to_room(message, room_id)
    
    async def broadcast_notification(self, notification_data: dict, user_id: int):
        """Отправка уведомления пользователю."""
        message = {
            "type": "notification",
            "data": notification_data
        }
        await self.send_personal_message(message, user_id)
    
    async def handle_websocket_message(self, websocket: WebSocket, user_id: int, data: dict):
        """Обработка входящих WebSocket сообщений."""
        message_type = data.get("type")
        
        if message_type == "typing":
            room_id = data.get("room_id")
            is_typing = data.get("is_typing", False)
            await self.broadcast_typing(user_id, room_id, is_typing)
        
        elif message_type == "ping":
            # Отвечаем на ping
            await self.send_personal_message({"type": "pong"}, user_id)
        
        elif message_type == "join_room":
            room_id = data.get("room_id")
            if room_id:
                await self.join_room(user_id, room_id)
        
        elif message_type == "leave_room":
            room_id = data.get("room_id")
            if room_id:
                await self.leave_room(user_id, room_id)
    
    async def join_room(self, user_id: int, room_id: int):
        """Подключение пользователя к комнате."""
        if room_id not in self.room_connections:
            self.room_connections[room_id] = set()
        self.room_connections[room_id].add(user_id)
        
        logger.info(f"Пользователь {user_id} присоединился к комнате {room_id}")
    
    async def leave_room(self, user_id: int, room_id: int):
        """Отключение пользователя от комнаты."""
        if room_id in self.room_connections:
            self.room_connections[room_id].discard(user_id)
            if not self.room_connections[room_id]:
                del self.room_connections[room_id]
        
        logger.info(f"Пользователь {user_id} покинул комнату {room_id}")
    
    def get_online_users_count(self, room_id: int) -> int:
        """Получение количества онлайн пользователей в комнате."""
        return len(self.room_connections.get(room_id, set()))
    
    def get_typing_users(self, room_id: int) -> List[int]:
        """Получение списка печатающих пользователей в комнате."""
        return list(self.typing_users.get(room_id, set()))


# Глобальный экземпляр менеджера
manager = ConnectionManager()


class WebSocketHandler:
    """Обработчик WebSocket соединений."""
    
    def __init__(self, manager: ConnectionManager):
        self.manager = manager
    
    async def handle_connection(self, websocket: WebSocket, user_id: int):
        """Обработка WebSocket соединения."""
        await self.manager.connect(websocket, user_id)
        
        try:
            while True:
                # Получаем сообщение
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # Обрабатываем сообщение
                await self.manager.handle_websocket_message(websocket, user_id, message_data)
                
        except WebSocketDisconnect:
            self.manager.disconnect(user_id)
            await self.manager.broadcast_user_online(user_id, False)
        except Exception as e:
            logger.error(f"Ошибка WebSocket соединения для пользователя {user_id}: {e}")
            self.manager.disconnect(user_id)
            await self.manager.broadcast_user_online(user_id, False)
