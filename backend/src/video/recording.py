"""
Система записи видео звонков
"""
import asyncio
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import aiofiles
from src.core.config_log import logger


class RecordingManager:
    """Менеджер записи видео звонков"""
    
    def __init__(self, recordings_dir: str = "recordings"):
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(exist_ok=True)
        self.active_recordings: Dict[str, Dict] = {}
        self.recording_metadata: Dict[str, Dict] = {}
    
    async def start_recording(self, room_code: str, user_id: str, user_name: str) -> Dict[str, Any]:
        """Начало записи комнаты"""
        try:
            if room_code in self.active_recordings:
                return {
                    "success": False,
                    "message": "Запись уже ведется в этой комнате"
                }
            
            # Создаем уникальное имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            recording_id = f"{room_code}_{timestamp}"
            recording_file = self.recordings_dir / f"{recording_id}.json"
            
            # Инициализируем запись
            recording_data = {
                "recording_id": recording_id,
                "room_code": room_code,
                "started_by": user_id,
                "started_by_name": user_name,
                "started_at": datetime.now().isoformat(),
                "ended_at": None,
                "participants": [],
                "events": [],
                "chat_messages": [],
                "webrtc_events": [],
                "file_path": str(recording_file),
                "is_active": True
            }
            
            # Сохраняем метаданные
            async with aiofiles.open(recording_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(recording_data, ensure_ascii=False, indent=2))
            
            self.active_recordings[room_code] = recording_data
            self.recording_metadata[recording_id] = recording_data
            
            logger.info(f"Начата запись комнаты {room_code} пользователем {user_name}")
            
            return {
                "success": True,
                "recording_id": recording_id,
                "message": "Запись начата"
            }
            
        except Exception as e:
            logger.error(f"Ошибка начала записи комнаты {room_code}: {e}")
            return {
                "success": False,
                "message": f"Ошибка начала записи: {str(e)}"
            }
    
    async def stop_recording(self, room_code: str, user_id: str) -> Dict[str, Any]:
        """Остановка записи комнаты"""
        try:
            if room_code not in self.active_recordings:
                return {
                    "success": False,
                    "message": "Активная запись не найдена"
                }
            
            recording_data = self.active_recordings[room_code]
            recording_id = recording_data["recording_id"]
            
            # Завершаем запись
            recording_data["ended_at"] = datetime.now().isoformat()
            recording_data["ended_by"] = user_id
            recording_data["is_active"] = False
            
            # Сохраняем финальные данные
            recording_file = Path(recording_data["file_path"])
            async with aiofiles.open(recording_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(recording_data, ensure_ascii=False, indent=2))
            
            # Удаляем из активных записей
            del self.active_recordings[room_code]
            
            logger.info(f"Остановлена запись комнаты {room_code}")
            
            return {
                "success": True,
                "recording_id": recording_id,
                "message": "Запись остановлена"
            }
            
        except Exception as e:
            logger.error(f"Ошибка остановки записи комнаты {room_code}: {e}")
            return {
                "success": False,
                "message": f"Ошибка остановки записи: {str(e)}"
            }
    
    async def add_participant(self, room_code: str, user_id: str, user_name: str, action: str = "joined"):
        """Добавление участника в запись"""
        try:
            if room_code not in self.active_recordings:
                return
            
            recording_data = self.active_recordings[room_code]
            participant_event = {
                "type": "participant_event",
                "action": action,  # joined, left
                "user_id": user_id,
                "user_name": user_name,
                "timestamp": datetime.now().isoformat()
            }
            
            recording_data["events"].append(participant_event)
            
            # Обновляем список участников
            if action == "joined":
                # Проверяем, не добавлен ли уже участник
                existing_participant = next(
                    (p for p in recording_data["participants"] if p["user_id"] == user_id), 
                    None
                )
                if not existing_participant:
                    recording_data["participants"].append({
                        "user_id": user_id,
                        "user_name": user_name,
                        "joined_at": datetime.now().isoformat()
                    })
            elif action == "left":
                # Удаляем участника из списка
                recording_data["participants"] = [
                    p for p in recording_data["participants"] if p["user_id"] != user_id
                ]
            
            # Сохраняем изменения
            await self._save_recording_data(room_code)
            
        except Exception as e:
            logger.error(f"Ошибка добавления участника в запись: {e}")
    
    async def add_chat_message(self, room_code: str, user_id: str, user_name: str, message: str):
        """Добавление сообщения чата в запись"""
        try:
            if room_code not in self.active_recordings:
                return
            
            recording_data = self.active_recordings[room_code]
            chat_event = {
                "type": "chat_message",
                "user_id": user_id,
                "user_name": user_name,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            
            recording_data["chat_messages"].append(chat_event)
            recording_data["events"].append(chat_event)
            
            # Сохраняем изменения
            await self._save_recording_data(room_code)
            
        except Exception as e:
            logger.error(f"Ошибка добавления сообщения чата в запись: {e}")
    
    async def add_webrtc_event(self, room_code: str, event_type: str, user_id: str, data: Dict[str, Any]):
        """Добавление WebRTC события в запись"""
        try:
            if room_code not in self.active_recordings:
                return
            
            recording_data = self.active_recordings[room_code]
            webrtc_event = {
                "type": "webrtc_event",
                "event_type": event_type,
                "user_id": user_id,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            recording_data["webrtc_events"].append(webrtc_event)
            recording_data["events"].append(webrtc_event)
            
            # Сохраняем изменения
            await self._save_recording_data(room_code)
            
        except Exception as e:
            logger.error(f"Ошибка добавления WebRTC события в запись: {e}")
    
    async def add_user_action(self, room_code: str, user_id: str, user_name: str, action: str, value: Any = None):
        """Добавление действия пользователя в запись"""
        try:
            if room_code not in self.active_recordings:
                return
            
            recording_data = self.active_recordings[room_code]
            action_event = {
                "type": "user_action",
                "user_id": user_id,
                "user_name": user_name,
                "action": action,
                "value": value,
                "timestamp": datetime.now().isoformat()
            }
            
            recording_data["events"].append(action_event)
            
            # Сохраняем изменения
            await self._save_recording_data(room_code)
            
        except Exception as e:
            logger.error(f"Ошибка добавления действия пользователя в запись: {e}")
    
    async def _save_recording_data(self, room_code: str):
        """Сохранение данных записи"""
        try:
            if room_code not in self.active_recordings:
                return
            
            recording_data = self.active_recordings[room_code]
            recording_file = Path(recording_data["file_path"])
            
            async with aiofiles.open(recording_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(recording_data, ensure_ascii=False, indent=2))
                
        except Exception as e:
            logger.error(f"Ошибка сохранения данных записи: {e}")
    
    def is_recording_active(self, room_code: str) -> bool:
        """Проверка активности записи"""
        return room_code in self.active_recordings
    
    def get_recording_info(self, room_code: str) -> Optional[Dict[str, Any]]:
        """Получение информации о записи"""
        return self.active_recordings.get(room_code)
    
    async def get_recordings_list(self, room_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получение списка записей"""
        try:
            recordings = []
            
            # Сканируем директорию записей
            for recording_file in self.recordings_dir.glob("*.json"):
                try:
                    async with aiofiles.open(recording_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        recording_data = json.loads(content)
                        
                        # Фильтруем по комнате если указана
                        if room_code and recording_data.get("room_code") != room_code:
                            continue
                        
                        # Добавляем только основную информацию
                        recordings.append({
                            "recording_id": recording_data.get("recording_id"),
                            "room_code": recording_data.get("room_code"),
                            "started_by": recording_data.get("started_by"),
                            "started_by_name": recording_data.get("started_by_name"),
                            "started_at": recording_data.get("started_at"),
                            "ended_at": recording_data.get("ended_at"),
                            "participants_count": len(recording_data.get("participants", [])),
                            "events_count": len(recording_data.get("events", [])),
                            "chat_messages_count": len(recording_data.get("chat_messages", [])),
                            "is_active": recording_data.get("is_active", False),
                            "file_path": recording_data.get("file_path")
                        })
                        
                except Exception as e:
                    logger.error(f"Ошибка чтения файла записи {recording_file}: {e}")
                    continue
            
            # Сортируем по дате начала (новые сначала)
            recordings.sort(key=lambda x: x.get("started_at", ""), reverse=True)
            
            return recordings
            
        except Exception as e:
            logger.error(f"Ошибка получения списка записей: {e}")
            return []
    
    async def get_recording_details(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """Получение детальной информации о записи"""
        try:
            # Ищем файл записи
            recording_file = self.recordings_dir / f"{recording_id}.json"
            
            if not recording_file.exists():
                return None
            
            async with aiofiles.open(recording_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
                
        except Exception as e:
            logger.error(f"Ошибка получения деталей записи {recording_id}: {e}")
            return None
    
    async def delete_recording(self, recording_id: str) -> bool:
        """Удаление записи"""
        try:
            recording_file = self.recordings_dir / f"{recording_id}.json"
            
            if recording_file.exists():
                recording_file.unlink()
                logger.info(f"Удалена запись {recording_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка удаления записи {recording_id}: {e}")
            return False


# Глобальный экземпляр менеджера записей
recording_manager = RecordingManager()
