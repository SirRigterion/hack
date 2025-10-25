from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import string
import random
from datetime import datetime, timedelta
import json

from src.db.models import VideoRoom, VideoParticipant, RoomInvitation, RoomEvent, User, MediaStream
from src.video.schemas import VideoRoomCreate, RoomInvitationCreate
from src.core.config_log import logger


class VideoService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_room_code(self) -> str:
        """Генерация уникального кода комнаты"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            result = await self.db.execute(
                select(VideoRoom).where(VideoRoom.room_code == code)
            )
            if result.scalar_one_or_none() is None:
                return code

    async def create_room(self, room_data: VideoRoomCreate, user_id: int) -> VideoRoom:
        """Создание новой видеокомнаты"""
        try:
            # Используем переданный room_code или генерируем новый
            room_code = room_data.room_code or await self.generate_room_code()
            
            room = VideoRoom(
                room_name=room_data.room_name,
                room_description=room_data.room_description,
                room_code=room_code,
                room_url=f"/video/room/{room_code}",
                created_by=user_id,
                is_private=room_data.is_private,
                max_participants=room_data.max_participants,
                recording_enabled=room_data.recording_enabled,
                waiting_room_enabled=room_data.waiting_room_enabled
            )
            
            self.db.add(room)
            await self.db.flush()  # Получаем room_id
        
            # Создаем запись участника (создатель комнаты)
            participant = VideoParticipant(
                room_id=room.room_id,
                user_id=user_id,
                role="host",
                        permissions='{"moderate": true, "record": true, "invite": true}',
                        is_online=True
            )
            
            self.db.add(participant)
                    
            # Записываем событие создания комнаты
            event = RoomEvent(
                room_id=room.room_id,
                participant_id=None,  # Будет установлено после коммита
                event_type="room_created",
                event_data=f'{{"user_id": {user_id}, "room_name": "{room_data.room_name}"}}'
            )
            self.db.add(event)
            
            await self.db.commit()
            await self.db.refresh(room)
            await self.db.refresh(participant)
            
            # Обновляем event с participant_id
            event.participant_id = participant.participant_id
            await self.db.commit()
            
            logger.info(f"Создана видеокомната {room.room_id} пользователем {user_id}")
            return room
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка создания видеокомнаты: {e}")
            raise

    async def join_room(self, room_code: str, user_id: int) -> Optional[VideoRoom]:
        """Присоединение пользователя к комнате"""
        # Приводим код комнаты к верхнему регистру для consistency
        room_code_upper = room_code.upper()
        
        result = await self.db.execute(
            select(VideoRoom).where(
                and_(
                    VideoRoom.room_code == room_code_upper,
                    VideoRoom.is_active == True
                )
            )
        )
        room = result.scalar_one_or_none()
        
        if not room:
            return None
        
        # Проверяем, не присоединен ли пользователь уже
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room.room_id,
                    VideoParticipant.user_id == user_id
                )
            )
        )
        existing_participant = result.scalar_one_or_none()
        
        if not existing_participant:
            # Создаем новую запись участника
            participant = VideoParticipant(
                room_id=room.room_id,
                user_id=user_id,
                role="participant",
                permissions='{}',
                is_online=True
            )
            self.db.add(participant)
            
            # Записываем событие присоединения
            event = RoomEvent(
                room_id=room.room_id,
                participant_id=None,  # Будет установлено после коммита
                event_type="join",
                event_data=f'{{"user_id": {user_id}}}'
            )
            self.db.add(event)
            
            await self.db.commit()
            await self.db.refresh(participant)
            
            # Обновляем event с participant_id
            event.participant_id = participant.participant_id
            await self.db.commit()
        else:
            # Обновляем существующего участника
            existing_participant.is_online = True
            existing_participant.left_at = None
            await self.db.commit()
        
        return room

    async def leave_room(self, room_id: int, user_id: int):
        """Выход пользователя из комнаты"""
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room_id,
                    VideoParticipant.user_id == user_id
                )
            )
        )
        participant = result.scalar_one_or_none()
        
        if participant:
            participant.left_at = datetime.now()
            participant.is_online = False
            
            # Записываем событие выхода
            event = RoomEvent(
                room_id=room_id,
                participant_id=participant.participant_id,
                event_type="leave",
                event_data='{}'
            )
            self.db.add(event)
            
            await self.db.commit()

    async def create_invitation(self, room_id: int, invitation_data: RoomInvitationCreate, inviter_id: int) -> RoomInvitation:
        """Создание приглашения в комнату"""
        # Валидация: должен быть указан либо email, либо user_id
        if not invitation_data.invited_email and not invitation_data.invited_user_id:
            raise ValueError("Необходимо указать invited_email или invited_user_id")
        
        # Если указан invited_user_id, проверяем существование пользователя
        if invitation_data.invited_user_id:
            result = await self.db.execute(
                select(User).where(User.user_id == invitation_data.invited_user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError(f"Пользователь с ID {invitation_data.invited_user_id} не найден")
        
        invitation_code = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        expires_at = datetime.now() + timedelta(hours=invitation_data.expires_hours)
        
        invitation = RoomInvitation(
            room_id=room_id,
            invited_by=inviter_id,
            invited_user_id=invitation_data.invited_user_id,
            invited_email=invitation_data.invited_email,
            invitation_code=invitation_code,
            expires_at=expires_at
        )
        
        self.db.add(invitation)
        await self.db.commit()
        await self.db.refresh(invitation)
        
        return invitation

    async def get_room_by_code(self, room_code: str) -> Optional[VideoRoom]:
        """Получение комнаты по коду"""
        room_code_upper = room_code.upper()
        result = await self.db.execute(
            select(VideoRoom).where(
                and_(
                    VideoRoom.room_code == room_code_upper,
                    VideoRoom.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_room_participants(self, room_id: int) -> List[VideoParticipant]:
        """Получение списка участников комнаты"""
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room_id,
                    VideoParticipant.is_online == True
                )
            )
        )
        return result.scalars().all()

    async def update_participant_status(self, room_id: int, user_id: int, **kwargs):
        """Обновление статуса участника"""
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room_id,
                    VideoParticipant.user_id == user_id
                )
            )
        )
        participant = result.scalar_one_or_none()
        
        if participant:
            for key, value in kwargs.items():
                if hasattr(participant, key):
                    setattr(participant, key, value)
            
            participant.last_activity = datetime.now()
            await self.db.commit()

    async def get_user_rooms(self, user_id: int) -> List[VideoRoom]:
        """Получение списка комнат пользователя"""
        result = await self.db.execute(
            select(VideoRoom).join(
                VideoParticipant,
                VideoRoom.room_id == VideoParticipant.room_id
            ).where(
                and_(
                    VideoParticipant.user_id == user_id,
                    VideoRoom.is_active == True
                )
            )
        )
        return result.scalars().all()

    async def get_room_by_id(self, room_id: int) -> Optional[VideoRoom]:
        """Получение комнаты по ID"""
        result = await self.db.execute(
            select(VideoRoom).where(VideoRoom.room_id == room_id)
        )
        return result.scalar_one_or_none()

    async def create_media_stream(self, room_id: int, participant_id: int, stream_type: str, stream_id_webrtc: str) -> MediaStream:
        """Создание медиапотока"""
        try:
            stream = MediaStream(
                room_id=room_id,
                participant_id=participant_id,
                stream_type=stream_type,
                stream_id_webrtc=stream_id_webrtc,
                is_active=True
            )
            
            self.db.add(stream)
            await self.db.commit()
            await self.db.refresh(stream)
            
            logger.info(f"Создан медиапоток {stream.stream_id} для участника {participant_id}")
            return stream
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка создания медиапотока: {e}")
            raise

    async def end_media_stream(self, stream_id: int):
        """Завершение медиапотока"""
        try:
            result = await self.db.execute(
                select(MediaStream).where(MediaStream.stream_id == stream_id)
            )
            stream = result.scalar_one_or_none()
            
            if stream:
                stream.is_active = False
                stream.ended_at = datetime.now()
                await self.db.commit()
                logger.info(f"Завершен медиапоток {stream_id}")
                
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка завершения медиапотока: {e}")
            raise

    async def get_active_streams(self, room_id: int) -> List[MediaStream]:
        """Получение активных медиапотоков в комнате"""
        result = await self.db.execute(
            select(MediaStream).where(
                and_(
                    MediaStream.room_id == room_id,
                    MediaStream.is_active == True
                )
            )
        )
        return result.scalars().all()

    async def get_participant_by_user_id(self, room_id: int, user_id: int) -> Optional[VideoParticipant]:
        """Получение участника по user_id в комнате"""
        result = await self.db.execute(
            select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room_id,
                    VideoParticipant.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_participant_stream_status(self, room_id: int, user_id: int, stream_type: str, is_active: bool):
        """Обновление статуса потока участника"""
        try:
            participant = await self.get_participant_by_user_id(room_id, user_id)
            if not participant:
                return
            
            if stream_type == "audio":
                # Обновляем статус микрофона через is_muted
                participant.is_muted = not is_active
            elif stream_type == "video":
                # Обновляем статус видео через is_video_enabled
                participant.is_video_enabled = is_active
            elif stream_type == "screen":
                # Обновляем статус демонстрации экрана
                participant.is_screen_sharing = is_active
            
            participant.last_activity = datetime.now()
            await self.db.commit()
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка обновления статуса потока: {e}")
            raise

    async def get_room_statistics(self, room_id: int) -> dict:
        """Получение статистики комнаты"""
        try:
            # Количество участников
            participants_count = await self.db.execute(
                select(func.count(VideoParticipant.participant_id)).where(
                    and_(
                        VideoParticipant.room_id == room_id,
                        VideoParticipant.is_online == True
                    )
                )
            )
            participants_count = participants_count.scalar()
            
            # Количество активных потоков
            streams_count = await self.db.execute(
                select(func.count(MediaStream.stream_id)).where(
                    and_(
                        MediaStream.room_id == room_id,
                        MediaStream.is_active == True
                    )
                )
            )
            streams_count = streams_count.scalar()
            
            # Последние события
            events_result = await self.db.execute(
                select(RoomEvent).where(RoomEvent.room_id == room_id)
                .order_by(RoomEvent.created_at.desc())
                .limit(10)
            )
            recent_events = events_result.scalars().all()
            
            return {
                "participants_count": participants_count,
                "active_streams_count": streams_count,
                "recent_events": [
                    {
                        "event_type": event.event_type,
                        "created_at": event.created_at.isoformat(),
                        "event_data": json.loads(event.event_data) if event.event_data else {}
                    }
                    for event in recent_events
                ]
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики комнаты: {e}")
            return {
                "participants_count": 0,
                "active_streams_count": 0,
                "recent_events": []
            }