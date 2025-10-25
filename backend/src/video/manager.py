from fastapi import WebSocket
import json
import uuid
from typing import Dict, List, Optional, Set
from datetime import datetime
import asyncio
from src.core.config_log import logger
from src.video.recording import recording_manager


class ConnectionManager:
    def __init__(self):
        # room_id -> список WebSocket подключений
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # user_id -> WebSocket (для личных сообщений)
        self.user_connections: Dict[str, WebSocket] = {}
        # user_id -> room_id (для быстрого поиска комнаты пользователя)
        self.user_rooms: Dict[str, str] = {}
        # room_id -> информация о комнате
        self.rooms_info: Dict[str, Dict] = {}
        # room_id -> список участников с их метаданными
        self.room_participants: Dict[str, List[Dict]] = {}
        # room_id -> Set[user_id] для быстрого поиска участников
        self.room_user_ids: Dict[str, Set[str]] = {}
        # WebRTC соединения: (room_id, user_id) -> peer_connection_info
        self.webrtc_connections: Dict[tuple, Dict] = {}
        # Информация о пользователях: user_id -> user_info
        self.user_info: Dict[str, Dict] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str, user_name: str = "User"):
        try:   
            await websocket.accept()
            logger.info(f"WebSocket подключен: комната={room_id}, пользователь={user_id}")
        
            # Инициализация комнаты если не существует
            if room_id not in self.active_connections:
                self.active_connections[room_id] = []
                self.rooms_info[room_id] = {
                    "participants": [],
                    "created_at": datetime.now(),
                    "is_recording": False,
                    "max_participants": 50
                }
                self.room_participants[room_id] = []
                self.room_user_ids[room_id] = set()
            
            # Проверяем лимит участников
            if len(self.room_user_ids[room_id]) >= self.rooms_info[room_id]["max_participants"]:
                await websocket.close(code=1013, reason="Room is full")
                return
                
            # Добавляем соединение
            self.active_connections[room_id].append(websocket)
            self.user_connections[user_id] = websocket
            self.user_rooms[user_id] = room_id
            
            # Сохраняем информацию о пользователе
            self.user_info[user_id] = {
                "user_name": user_name,
                "joined_at": datetime.now().isoformat(),
                "is_audio_muted": False,  # По умолчанию микрофон включен
                "is_video_enabled": True,  # По умолчанию видео включено
                "is_screen_sharing": False,
                "role": "participant"
            }
            
            # Добавляем пользователя в информацию о комнате
            participant_info = {
                "user_id": user_id,
                "user_name": user_name,
                "joined_at": datetime.now().isoformat(),
                "is_audio_muted": False,
                "is_video_enabled": True,
                "is_screen_sharing": False,
                "role": "participant"
            }
        
            if user_id not in self.room_user_ids[room_id]:
                self.room_user_ids[room_id].add(user_id)
                self.rooms_info[room_id]["participants"].append(user_id)
                self.room_participants[room_id].append(participant_info)

            # Отправляем текущему пользователю список всех участников
            await self.send_personal_message({
                "type": "participants_list",
                "participants": self.room_participants[room_id],
                "your_id": user_id,
                "room_id": room_id
            }, websocket)

            # Уведомляем других участников о новом подключении
            join_message = {
                "type": "user_joined",
                "user_id": user_id,
                "user_name": user_name,
                "room_id": room_id,
                "timestamp": datetime.now().isoformat(),
                "participants_count": len(self.room_participants[room_id])
            }
            await self.broadcast_to_room(join_message, room_id, websocket)
            
            # Добавляем участника в запись если она активна
            if recording_manager.is_recording_active(room_id):
                await recording_manager.add_participant(room_id, user_id, user_name, "joined")
            
        except Exception as e:
            logger.error(f"Ошибка подключения WebSocket: {e}")
            try:
                await websocket.close(code=1011, reason="Internal error")
            except:
                pass

    def disconnect(self, websocket: WebSocket, room_id: str, user_id: str):
        try:
            logger.info(f"WebSocket отключен: комната={room_id}, пользователь={user_id}")
            
            if room_id in self.active_connections:
                if websocket in self.active_connections[room_id]:
                    self.active_connections[room_id].remove(websocket)
            
            # Удаляем пользователя из информации о комнате
            if user_id in self.room_user_ids.get(room_id, set()):
                self.room_user_ids[room_id].discard(user_id)
                self.rooms_info[room_id]["participants"] = [uid for uid in self.rooms_info[room_id]["participants"] if uid != user_id]
                self.room_participants[room_id] = [p for p in self.room_participants[room_id] if p["user_id"] != user_id]
            
            # Очищаем комнату если она пустая
            if room_id in self.active_connections and len(self.active_connections[room_id]) == 0:
                del self.active_connections[room_id]
                if room_id in self.rooms_info:
                    del self.rooms_info[room_id]
                if room_id in self.room_participants:
                    del self.room_participants[room_id]
                if room_id in self.room_user_ids:
                    del self.room_user_ids[room_id]

            # Удаляем пользовательские соединения
            if user_id in self.user_connections:
                del self.user_connections[user_id]
                if user_id in self.user_rooms:
                    del self.user_rooms[user_id]
            if user_id in self.user_info:
                del self.user_info[user_id]
                    
            # Очищаем WebRTC соединения пользователя
            webrtc_keys_to_remove = [key for key in self.webrtc_connections.keys() if key[1] == user_id]
            for key in webrtc_keys_to_remove:
                del self.webrtc_connections[key]
            
            # Добавляем участника в запись если она активна
            if recording_manager.is_recording_active(room_id):
                user_info = self.user_info.get(user_id, {})
                user_name = user_info.get("user_name", f"User {user_id}")
                recording_manager.add_participant(room_id, user_id, user_name, "left")
                
        except Exception as e:
            logger.error(f"Ошибка отключения WebSocket: {e}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"Ошибка отправки личного сообщения: {e}")

    async def send_to_user(self, message: dict, user_id: str):
        if user_id in self.user_connections:
            try:
                await self.user_connections[user_id].send_json(message)
            except Exception as e:
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")

    async def broadcast_to_room(self, message: dict, room_id: str, sender_websocket: WebSocket = None):
        if room_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[room_id]:
                if connection != sender_websocket:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        print(f"Ошибка отправки сообщения в комнату {room_id}: {e}")
                        disconnected.append(connection)
            
            # Удаляем отключенные соединения
            for connection in disconnected:
                self.active_connections[room_id].remove(connection)

    async def handle_webrtc_signal(self, data: dict, room_id: str, sender_websocket: WebSocket):
        """Обработка WebRTC сигналов (offer, answer, ice candidate)"""
        try:
            signal = data.get("signal", {})
            target_user_id = data.get("target_user_id")
            
            # Получаем sender_user_id из WebSocket соединения
            sender_user_id = None
            for user_id, ws in self.user_connections.items():
                if ws == sender_websocket:
                    sender_user_id = user_id
                    break
            
            if not sender_user_id:
                logger.warning("Не удалось определить отправителя WebRTC сигнала")
                return
            
            signal_type = signal.get("type")
            logger.info(f"WebRTC сигнал: {signal_type} от {sender_user_id} к {target_user_id}")
            
            # Валидация сигнала
            if not signal_type:
                logger.warning("Неполный WebRTC сигнал")
                return
            
            # Создаем сообщение сигнала
            signal_message = {
                "type": "webrtc_signal",
                "signal": signal,
                "target_user_id": target_user_id,
                "from_user_id": sender_user_id,
                "timestamp": datetime.now().isoformat()
            }
        
            # Если указан конкретный получатель, отправляем только ему
            if target_user_id:
                if target_user_id in self.user_connections:
                    await self.send_to_user(signal_message, target_user_id)
                    logger.info(f"WebRTC сигнал отправлен пользователю {target_user_id}")
                else:
                    logger.warning(f"Получатель {target_user_id} не найден")
            else:
                # Иначе рассылаем всем в комнате кроме отправителя
                await self.broadcast_to_room(signal_message, room_id, sender_websocket)
                logger.info(f"WebRTC сигнал разослан всем в комнате {room_id}")
                    
                # Сохраняем информацию о соединении для статистики
                if signal_type in ["offer", "answer"]:
                    connection_key = (room_id, sender_user_id)
                    if connection_key not in self.webrtc_connections:
                        self.webrtc_connections[connection_key] = {
                            "created_at": datetime.now(),
                            "last_signal": signal_type,
                            "signals_count": 0
                        }
                    self.webrtc_connections[connection_key]["last_signal"] = signal_type
                    self.webrtc_connections[connection_key]["signals_count"] += 1
                
        except Exception as e:
            logger.error(f"Ошибка обработки WebRTC сигнала: {e}")

    async def handle_chat_message(self, data: dict, room_id: str, sender_websocket: WebSocket):
        """Обработка сообщений чата"""
        # Получаем информацию о пользователе из WebSocket соединения
        sender_user_id = None
        for user_id, ws in self.user_connections.items():
            if ws == sender_websocket:
                sender_user_id = user_id
                break
        
        if not sender_user_id:
            logger.warning("Не удалось определить отправителя сообщения чата")
            return
            
        user_info = self.user_info.get(sender_user_id, {})
        
        chat_message = {
            "type": "chat_message",
            "message_id": str(uuid.uuid4()),
            "user_id": sender_user_id,
            "user_name": user_info.get("user_name", f"User {sender_user_id}"),
            "message": data.get("message", ""),
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast_to_room(chat_message, room_id, sender_websocket)
        
        # Добавляем сообщение в запись если она активна
        if recording_manager.is_recording_active(room_id):
            await recording_manager.add_chat_message(room_id, sender_user_id, user_info.get("user_name", f"User {sender_user_id}"), data.get("message", ""))

    async def handle_user_action(self, data: dict, room_id: str, sender_websocket: WebSocket):
        """Обработка действий пользователя (mute/unmute, video on/off)"""
        # Получаем информацию о пользователе из WebSocket соединения
        sender_user_id = None
        for user_id, ws in self.user_connections.items():
            if ws == sender_websocket:
                sender_user_id = user_id
                break
        
        if not sender_user_id:
            logger.warning("Не удалось определить отправителя действия")
            return
            
        user_info = self.user_info.get(sender_user_id, {})
        action = data.get("action")
        
        action_message = {
            "type": "user_action",
            "user_id": sender_user_id,
            "user_name": user_info.get("user_name", f"User {sender_user_id}"),
            "action": action,
            "value": data.get("value"),
            "timestamp": datetime.now().isoformat()
        }
        
        # Обновляем статус участника
        for participant in self.room_participants.get(room_id, []):
            if participant["user_id"] == sender_user_id:
                if action == "mute":
                    participant["is_audio_muted"] = True
                    user_info["is_audio_muted"] = True
                elif action == "unmute":
                    participant["is_audio_muted"] = False
                    user_info["is_audio_muted"] = False
                elif action == "video_off":
                    participant["is_video_enabled"] = False
                    user_info["is_video_enabled"] = False
                elif action == "video_on":
                    participant["is_video_enabled"] = True
                    user_info["is_video_enabled"] = True
                elif action == "screen_share_start":
                    participant["is_screen_sharing"] = True
                    user_info["is_screen_sharing"] = True
                elif action == "screen_share_stop":
                    participant["is_screen_sharing"] = False
                    user_info["is_screen_sharing"] = False
                break
        
        await self.broadcast_to_room(action_message, room_id, sender_websocket)
        
        # Добавляем действие в запись если она активна
        if recording_manager.is_recording_active(room_id):
            await recording_manager.add_user_action(room_id, sender_user_id, user_info.get("user_name", f"User {sender_user_id}"), action, data.get("value"))

    async def handle_recording_control(self, data: dict, room_id: str, sender_websocket: WebSocket):
        """Обработка управления записью"""
        # Получаем информацию о пользователе из WebSocket соединения
        sender_user_id = None
        for user_id, ws in self.user_connections.items():
            if ws == sender_websocket:
                sender_user_id = user_id
                break
        
        if not sender_user_id:
            logger.warning("Не удалось определить отправителя команды записи")
            return
            
        action = data.get("action")
        recording_message = {
            "type": "recording_control",
            "action": action,  # start, stop, pause
            "user_id": sender_user_id,
            "timestamp": datetime.now().isoformat()
        }
        
        if action == "start":
            # Начинаем запись
            user_info = self.user_info.get(sender_user_id, {})
            user_name = user_info.get("user_name", f"User {sender_user_id}")
            result = await recording_manager.start_recording(room_id, sender_user_id, user_name)
            
            if result["success"]:
                self.rooms_info[room_id]["is_recording"] = True
                recording_message["recording_id"] = result["recording_id"]
                recording_message["message"] = result["message"]
            else:
                recording_message["message"] = result["message"]
                
        elif action in ["stop", "pause"]:
            # Останавливаем запись
            result = await recording_manager.stop_recording(room_id, sender_user_id)
            
            if result["success"]:
                self.rooms_info[room_id]["is_recording"] = False
                recording_message["recording_id"] = result["recording_id"]
                recording_message["message"] = result["message"]
            else:
                recording_message["message"] = result["message"]
            
        await self.broadcast_to_room(recording_message, room_id, sender_websocket)

    def get_room_info(self, room_id: str) -> Optional[Dict]:
        """Получить информацию о комнате"""
        return self.rooms_info.get(room_id)

    def get_room_participants(self, room_id: str) -> List[Dict]:
        """Получить список участников комнаты"""
        return self.room_participants.get(room_id, [])

    def get_user_room(self, user_id: str) -> Optional[str]:
        """Получить комнату пользователя"""
        return self.user_rooms.get(user_id)

    def is_user_in_room(self, user_id: str, room_id: str) -> bool:
        """Проверить, находится ли пользователь в комнате"""
        return user_id in self.room_user_ids.get(room_id, set())

    def get_room_stats(self, room_id: str) -> Dict:
        """Получить статистику комнаты"""
        participants = self.room_participants.get(room_id, [])
        active_connections = len(self.active_connections.get(room_id, []))
        
        # Статистика WebRTC соединений
        webrtc_stats = {}
        for (r_id, u_id), info in self.webrtc_connections.items():
            if r_id == room_id:
                webrtc_stats[u_id] = {
                    "signals_count": info["signals_count"],
                    "last_signal": info["last_signal"],
                    "created_at": info["created_at"].isoformat()
                }
        
        return {
            "room_id": room_id,
            "participants_count": len(participants),
            "active_connections": active_connections,
            "is_recording": self.rooms_info.get(room_id, {}).get("is_recording", False),
            "created_at": self.rooms_info.get(room_id, {}).get("created_at", datetime.now()).isoformat(),
            "webrtc_connections": webrtc_stats,
            "participants": [
                {
                    "user_id": p["user_id"],
                    "user_name": p["user_name"],
                    "is_audio_muted": p["is_audio_muted"],
                    "is_video_off": p["is_video_off"],
                    "is_screen_sharing": p["is_screen_sharing"],
                    "role": p.get("role", "participant")
                }
                for p in participants
            ]
        }

    async def send_room_stats(self, room_id: str):
        """Отправить статистику комнаты всем участникам"""
        stats = self.get_room_stats(room_id)
        stats_message = {
            "type": "room_stats",
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast_to_room(stats_message, room_id)

    async def handle_media_stream_event(self, data: dict, room_id: str, sender_websocket: WebSocket):
        """Обработка событий медиапотоков"""
        try:
            # Получаем информацию о пользователе из WebSocket соединения
            sender_user_id = None
            for user_id, ws in self.user_connections.items():
                if ws == sender_websocket:
                    sender_user_id = user_id
                    break
            
            if not sender_user_id:
                logger.warning("Не удалось определить отправителя события медиапотока")
                return
                
            event_type = data.get("event_type")  # "stream_started", "stream_ended", "stream_paused"
            stream_type = data.get("stream_type")  # "audio", "video", "screen"
            stream_id = data.get("stream_id")
            
            logger.info(f"Медиапоток событие: {event_type} для {stream_type} от {sender_user_id}")
            
            # Обновляем статус участника
            for participant in self.room_participants.get(room_id, []):
                if participant["user_id"] == sender_user_id:
                    if stream_type == "audio":
                        participant["is_audio_muted"] = event_type == "stream_ended"
                    elif stream_type == "video":
                        participant["is_video_enabled"] = event_type == "stream_started"
                    elif stream_type == "screen":
                        participant["is_screen_sharing"] = event_type == "stream_started"
                    break
            
            # Отправляем обновление всем участникам
            stream_message = {
                "type": "media_stream_event",
                "event_type": event_type,
                "user_id": sender_user_id,
                "stream_type": stream_type,
                "stream_id": stream_id,
                "timestamp": datetime.now().isoformat()
            }
            await self.broadcast_to_room(stream_message, room_id, sender_websocket)
            
        except Exception as e:
            logger.error(f"Ошибка обработки события медиапотока: {e}")

    async def cleanup_room(self, room_id: str):
        """Очистка комнаты при закрытии"""
        try:
            if room_id in self.active_connections:
                # Закрываем все соединения в комнате
                for websocket in self.active_connections[room_id]:
                    try:
                        await websocket.close(code=1000, reason="Room closed")
                    except:
                        pass
                
                # Очищаем данные комнаты
                del self.active_connections[room_id]
                if room_id in self.rooms_info:
                    del self.rooms_info[room_id]
                if room_id in self.room_participants:
                    del self.room_participants[room_id]
                if room_id in self.room_user_ids:
                    del self.room_user_ids[room_id]
                
                # Очищаем WebRTC соединения комнаты
                webrtc_keys_to_remove = [key for key in self.webrtc_connections.keys() if key[0] == room_id]
                for key in webrtc_keys_to_remove:
                    del self.webrtc_connections[key]
                
                logger.info(f"Комната {room_id} очищена")
                
        except Exception as e:
            logger.error(f"Ошибка очистки комнаты {room_id}: {e}")


# Глобальный экземпляр менеджера
manager = ConnectionManager()