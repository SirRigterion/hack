import asyncio
import json
from typing import Dict, List, Optional, Set
from datetime import datetime

# Импорты aiortc будут доступны только при установке пакета
try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
    from aiortc.contrib.signaling import TcpSocketSignaling
    from aiortc.rtcrtpsender import RTCRtpSender
    from aiortc import MediaStreamTrack, VideoStreamTrack, AudioStreamTrack
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False
    # Заглушки для случаев когда aiortc не установлен
    class RTCPeerConnection:
        pass
    class RTCSessionDescription:
        pass
    class RTCIceCandidate:
        pass
    class MediaStreamTrack:
        pass
    class VideoStreamTrack:
        pass
    class AudioStreamTrack:
        pass

try:
    import cv2
    import numpy as np
    from PIL import Image
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    import numpy as np

from src.core.config_log import logger


class WebRTCManager:
    """Менеджер WebRTC соединений для видеоконференций."""
    
    def __init__(self):
        self.connections: Dict[str, RTCPeerConnection] = {}
        self.rooms: Dict[int, Set[str]] = {}  # room_id -> set of connection_ids
        self.participants: Dict[str, Dict] = {}  # connection_id -> participant_data
        self.media_tracks: Dict[str, Dict[str, MediaStreamTrack]] = {}  # connection_id -> track_type -> track
        self.signaling = None
        if AIORTC_AVAILABLE:
            self.signaling = TcpSocketSignaling("localhost", 8080)
        
    async def create_connection(self, connection_id: str, room_id: int, participant_data: Dict) -> RTCPeerConnection:
        """Создание нового WebRTC соединения."""
        if not AIORTC_AVAILABLE:
            raise RuntimeError("aiortc не установлен. Установите: pip install aiortc")
        
        try:
            # Создаем новое соединение
            pc = RTCPeerConnection()
            
            # Настраиваем обработчики событий
            @pc.on("track")
            def on_track(track):
                logger.info(f"Получен трек {track.kind} от {connection_id}")
                self._handle_track(connection_id, track)
            
            @pc.on("iceconnectionstatechange")
            def on_ice_connection_state_change():
                logger.info(f"ICE соединение изменилось: {pc.iceConnectionState}")
                if pc.iceConnectionState == "failed":
                    asyncio.create_task(self._cleanup_connection(connection_id))
            
            @pc.on("connectionstatechange")
            def on_connection_state_change():
                logger.info(f"Состояние соединения изменилось: {pc.connectionState}")
                if pc.connectionState == "failed":
                    asyncio.create_task(self._cleanup_connection(connection_id))
            
            # Сохраняем соединение
            self.connections[connection_id] = pc
            
            # Добавляем в комнату
            if room_id not in self.rooms:
                self.rooms[room_id] = set()
            self.rooms[room_id].add(connection_id)
            
            # Сохраняем данные участника
            self.participants[connection_id] = {
                **participant_data,
                'room_id': room_id,
                'connected_at': datetime.now()
            }
            
            logger.info(f"Создано WebRTC соединение {connection_id} для комнаты {room_id}")
            return pc
            
        except Exception as e:
            logger.error(f"Ошибка создания WebRTC соединения: {e}")
            raise
    
    async def handle_offer(self, connection_id: str, offer_data: Dict) -> Dict:
        """Обработка WebRTC offer."""
        try:
            if connection_id not in self.connections:
                raise ValueError(f"Соединение {connection_id} не найдено")
            
            pc = self.connections[connection_id]
            
            # Создаем offer
            offer = RTCSessionDescription(
                sdp=offer_data['sdp'],
                type=offer_data['type']
            )
            
            await pc.setRemoteDescription(offer)
            
            # Создаем answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            return {
                'type': 'answer',
                'sdp': answer.sdp
            }
            
        except Exception as e:
            logger.error(f"Ошибка обработки offer: {e}")
            raise
    
    async def handle_answer(self, connection_id: str, answer_data: Dict):
        """Обработка WebRTC answer."""
        try:
            if connection_id not in self.connections:
                raise ValueError(f"Соединение {connection_id} не найдено")
            
            pc = self.connections[connection_id]
            
            answer = RTCSessionDescription(
                sdp=answer_data['sdp'],
                type=answer_data['type']
            )
            
            await pc.setRemoteDescription(answer)
            
        except Exception as e:
            logger.error(f"Ошибка обработки answer: {e}")
            raise
    
    async def handle_ice_candidate(self, connection_id: str, candidate_data: Dict):
        """Обработка ICE кандидата."""
        try:
            if connection_id not in self.connections:
                raise ValueError(f"Соединение {connection_id} не найдено")
            
            pc = self.connections[connection_id]
            
            candidate = RTCIceCandidate(
                candidate=candidate_data['candidate'],
                sdpMid=candidate_data.get('sdpMid'),
                sdpMLineIndex=candidate_data.get('sdpMLineIndex')
            )
            
            await pc.addIceCandidate(candidate)
            
        except Exception as e:
            logger.error(f"Ошибка обработки ICE кандидата: {e}")
            raise
    
    async def add_media_track(self, connection_id: str, track_type: str, track: MediaStreamTrack):
        """Добавление медиа трека."""
        try:
            if connection_id not in self.connections:
                raise ValueError(f"Соединение {connection_id} не найдено")
            
            pc = self.connections[connection_id]
            
            # Добавляем трек в соединение
            sender = pc.addTrack(track)
            
            # Настраиваем качество
            if hasattr(sender, 'setParameters'):
                params = sender.getParameters()
                if track_type == 'video':
                    params.encodings[0].maxBitrate = 2000000  # 2 Mbps
                    params.encodings[0].scaleResolutionDownBy = 1.0
                elif track_type == 'audio':
                    params.encodings[0].maxBitrate = 128000  # 128 kbps
                
                await sender.setParameters(params)
            
            # Сохраняем трек
            if connection_id not in self.media_tracks:
                self.media_tracks[connection_id] = {}
            self.media_tracks[connection_id][track_type] = track
            
            logger.info(f"Добавлен трек {track_type} для соединения {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка добавления медиа трека: {e}")
            raise
    
    async def remove_media_track(self, connection_id: str, track_type: str):
        """Удаление медиа трека."""
        try:
            if connection_id in self.media_tracks and track_type in self.media_tracks[connection_id]:
                track = self.media_tracks[connection_id][track_type]
                track.stop()
                del self.media_tracks[connection_id][track_type]
                
                logger.info(f"Удален трек {track_type} для соединения {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка удаления медиа трека: {e}")
            raise
    
    async def mute_audio(self, connection_id: str, muted: bool):
        """Включение/выключение аудио."""
        try:
            if connection_id in self.media_tracks and 'audio' in self.media_tracks[connection_id]:
                track = self.media_tracks[connection_id]['audio']
                if hasattr(track, 'muted'):
                    track.muted = muted
                else:
                    # Для кастомных треков
                    track._muted = muted
                
                logger.info(f"Аудио {'заглушено' if muted else 'включено'} для {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка управления аудио: {e}")
            raise
    
    async def mute_video(self, connection_id: str, muted: bool):
        """Включение/выключение видео."""
        try:
            if connection_id in self.media_tracks and 'video' in self.media_tracks[connection_id]:
                track = self.media_tracks[connection_id]['video']
                if hasattr(track, 'muted'):
                    track.muted = muted
                else:
                    # Для кастомных треков
                    track._muted = muted
                
                logger.info(f"Видео {'выключено' if muted else 'включено'} для {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка управления видео: {e}")
            raise
    
    async def start_screen_share(self, connection_id: str, screen_track: MediaStreamTrack):
        """Начало демонстрации экрана."""
        try:
            await self.add_media_track(connection_id, 'screen', screen_track)
            logger.info(f"Начата демонстрация экрана для {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка начала демонстрации экрана: {e}")
            raise
    
    async def stop_screen_share(self, connection_id: str):
        """Остановка демонстрации экрана."""
        try:
            await self.remove_media_track(connection_id, 'screen')
            logger.info(f"Остановлена демонстрация экрана для {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка остановки демонстрации экрана: {e}")
            raise
    
    async def get_room_participants(self, room_id: int) -> List[Dict]:
        """Получение списка участников комнаты."""
        participants = []
        
        if room_id in self.rooms:
            for connection_id in self.rooms[room_id]:
                if connection_id in self.participants:
                    participant_data = self.participants[connection_id].copy()
                    participant_data['connection_id'] = connection_id
                    
                    # Добавляем информацию о треках
                    if connection_id in self.media_tracks:
                        participant_data['active_tracks'] = list(self.media_tracks[connection_id].keys())
                    
                    participants.append(participant_data)
        
        return participants
    
    async def broadcast_to_room(self, room_id: int, message: Dict, exclude_connection: Optional[str] = None):
        """Отправка сообщения всем участникам комнаты."""
        if room_id in self.rooms:
            for connection_id in self.rooms[room_id]:
                if connection_id != exclude_connection:
                    await self._send_to_connection(connection_id, message)
    
    async def _send_to_connection(self, connection_id: str, message: Dict):
        """Отправка сообщения конкретному соединению."""
        try:
            # Здесь должна быть реализация отправки через WebSocket
            # Пока что просто логируем
            logger.info(f"Отправка сообщения {message} в соединение {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
    
    def _handle_track(self, connection_id: str, track: MediaStreamTrack):
        """Обработка полученного трека."""
        try:
            logger.info(f"Получен трек {track.kind} от {connection_id}")
            
            # Здесь можно добавить обработку трека
            # Например, сохранение в файл или ретрансляция другим участникам
            
        except Exception as e:
            logger.error(f"Ошибка обработки трека: {e}")
    
    async def _cleanup_connection(self, connection_id: str):
        """Очистка соединения."""
        try:
            # Останавливаем все треки
            if connection_id in self.media_tracks:
                for track in self.media_tracks[connection_id].values():
                    track.stop()
                del self.media_tracks[connection_id]
            
            # Закрываем соединение
            if connection_id in self.connections:
                await self.connections[connection_id].close()
                del self.connections[connection_id]
            
            # Удаляем из комнаты
            for room_id, participants in self.rooms.items():
                participants.discard(connection_id)
                if not participants:
                    del self.rooms[room_id]
                    break
            
            # Удаляем данные участника
            if connection_id in self.participants:
                del self.participants[connection_id]
            
            logger.info(f"Очищено соединение {connection_id}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки соединения: {e}")
    
    async def close_room(self, room_id: int):
        """Закрытие комнаты и всех соединений."""
        try:
            if room_id in self.rooms:
                # Получаем все соединения в комнате
                connections_to_close = list(self.rooms[room_id])
                
                # Закрываем все соединения
                for connection_id in connections_to_close:
                    await self._cleanup_connection(connection_id)
                
                logger.info(f"Закрыта комната {room_id}")
            
        except Exception as e:
            logger.error(f"Ошибка закрытия комнаты: {e}")


class MediaTrackFactory:
    """Фабрика для создания медиа треков."""
    
    @staticmethod
    def create_video_track(width: int = 640, height: int = 480, fps: int = 30) -> VideoStreamTrack:
        """Создание видео трека."""
        from src.video.tracks import CustomVideoTrack
        return CustomVideoTrack(width, height, fps)
    
    @staticmethod
    def create_audio_track() -> AudioStreamTrack:
        """Создание аудио трека."""
        from src.video.tracks import CustomAudioTrack
        return CustomAudioTrack()
    
    @staticmethod
    def create_screen_track() -> VideoStreamTrack:
        """Создание трека для демонстрации экрана."""
        from src.video.tracks import ScreenShareTrack
        return ScreenShareTrack()


# Глобальный экземпляр менеджера
webrtc_manager = WebRTCManager()
