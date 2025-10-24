from typing import List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

from src.db.database import get_db
from src.db.models import (
    User, VideoRoom, VideoParticipant, MediaStream, RoomRecording,
    RoomInvitation, RoomEvent, UserStatus
)
from src.video.schemas import (
    VideoRoomCreate, VideoRoomUpdate, VideoRoomResponse,
    VideoParticipantCreate, VideoParticipantUpdate, VideoParticipantResponse,
    MediaStreamCreate, MediaStreamUpdate, MediaStreamResponse,
    RoomRecordingCreate, RoomRecordingResponse,
    RoomInvitationCreate, RoomInvitationResponse,
    RoomEventCreate, RoomEventResponse,
    VideoRoomFilter, ParticipantFilter, RecordingFilter,
    WebRTCSignal, ParticipantStatusUpdate, RoomStatusUpdate
)
from src.video.utils import (
    RoomCodeGenerator, RoomURLGenerator, RoomValidator,
    FileManager, EventLogger
)
from src.video.webrtc_manager import webrtc_manager, MediaTrackFactory
from src.auth.auth import get_current_user
from src.core.config_log import logger

router = APIRouter(prefix="/video", tags=["video"])


# ==================== VIDEO ROOMS ====================

@router.post("/rooms", response_model=VideoRoomResponse)
async def create_video_room(
    room_data: VideoRoomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создание новой видеокомнаты."""
    try:
        # Валидация данных
        if not RoomValidator.validate_room_name(room_data.room_name):
            raise HTTPException(status_code=400, detail="Некорректное название комнаты")
        
        if not RoomValidator.validate_participant_limit(room_data.max_participants):
            raise HTTPException(status_code=400, detail="Некорректный лимит участников")
        
        # Генерируем уникальный код и URL
        room_code = RoomCodeGenerator.generate_room_code()
        room_url = RoomURLGenerator.generate_room_url(room_code)
        
        # Проверяем уникальность кода
        while True:
            existing_room = await db.execute(
                select(VideoRoom).where(VideoRoom.room_code == room_code)
            )
            if not existing_room.scalar_one_or_none():
                break
            room_code = RoomCodeGenerator.generate_room_code()
            room_url = RoomURLGenerator.generate_room_url(room_code)
        
        # Создаем комнату
        room = VideoRoom(
            room_name=room_data.room_name,
            room_description=room_data.room_description,
            room_code=room_code,
            room_url=room_url,
            created_by=current_user.user_id,
            is_private=room_data.is_private,
            max_participants=room_data.max_participants,
            recording_enabled=room_data.recording_enabled,
            waiting_room_enabled=room_data.waiting_room_enabled
        )
        
        db.add(room)
        await db.flush()  # Получаем room_id
        
        # Добавляем создателя как участника с ролью host
        participant = VideoParticipant(
            room_id=room.room_id,
            user_id=current_user.user_id,
            role="host",
            permissions={"can_mute_others": True, "can_remove_others": True, "can_start_recording": True}
        )
        
        db.add(participant)
        await db.commit()
        await db.refresh(room)
        
        # Логируем событие
        EventLogger.log_room_event(
            room_id=room.room_id,
            event_type="room_created",
            event_data={"created_by": current_user.user_id}
        )
        
        logger.info(f"Создана видеокомната {room.room_id} пользователем {current_user.user_id}")
        
        return VideoRoomResponse(
            room_id=room.room_id,
            room_name=room.room_name,
            room_description=room.room_description,
            room_code=room.room_code,
            room_url=room.room_url,
            is_private=room.is_private,
            max_participants=room.max_participants,
            recording_enabled=room.recording_enabled,
            waiting_room_enabled=room.waiting_room_enabled,
            created_at=room.created_at,
            created_by=room.created_by,
            is_active=room.is_active
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка создания видеокомнаты: {e}")
        raise HTTPException(status_code=500, detail="Ошибка создания видеокомнаты")


@router.get("/rooms", response_model=List[VideoRoomResponse])
async def get_video_rooms(
    filter_params: VideoRoomFilter = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка видеокомнат."""
    try:
        # Базовый запрос
        query = select(VideoRoom).options(selectinload(VideoRoom.participants))
        
        # Фильтры
        if filter_params.is_private is not None:
            query = query.where(VideoRoom.is_private == filter_params.is_private)
        
        if filter_params.is_active is not None:
            query = query.where(VideoRoom.is_active == filter_params.is_active)
        
        if filter_params.created_by:
            query = query.where(VideoRoom.created_by == filter_params.created_by)
        
        if filter_params.search_text:
            query = query.where(
                or_(
                    VideoRoom.room_name.ilike(f"%{filter_params.search_text}%"),
                    VideoRoom.room_description.ilike(f"%{filter_params.search_text}%")
                )
            )
        
        # Сортировка по времени создания (новые сначала)
        query = query.order_by(VideoRoom.created_at.desc())
        
        # Пагинация
        query = query.offset(filter_params.offset).limit(filter_params.limit)
        
        result = await db.execute(query)
        rooms = result.scalars().all()
        
        # Формируем ответ
        response = []
        for room in rooms:
            participants_count = len(room.participants)
            response.append(VideoRoomResponse(
                room_id=room.room_id,
                room_name=room.room_name,
                room_description=room.room_description,
                room_code=room.room_code,
                room_url=room.room_url,
                is_private=room.is_private,
                max_participants=room.max_participants,
                recording_enabled=room.recording_enabled,
                waiting_room_enabled=room.waiting_room_enabled,
                created_at=room.created_at,
                created_by=room.created_by,
                is_active=room.is_active,
                participants_count=participants_count
            ))
        
        return response
        
    except Exception as e:
        logger.error(f"Ошибка получения видеокомнат: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения видеокомнат")


@router.get("/rooms/{room_code}", response_model=VideoRoomResponse)
async def get_video_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о видеокомнате по коду."""
    try:
        # Получаем комнату
        room_query = select(VideoRoom).where(VideoRoom.room_code == room_code)
        room_result = await db.execute(room_query)
        room = room_result.scalar_one_or_none()
        
        if not room:
            raise HTTPException(status_code=404, detail="Видеокомната не найдена")
        
        if not room.is_active:
            raise HTTPException(status_code=410, detail="Видеокомната неактивна")
        
        # Получаем количество участников
        count_query = select(func.count(VideoParticipant.participant_id)).where(
            and_(
                VideoParticipant.room_id == room.room_id,
                VideoParticipant.is_online == True
            )
        )
        count_result = await db.execute(count_query)
        participants_count = count_result.scalar()
        
        return VideoRoomResponse(
            room_id=room.room_id,
            room_name=room.room_name,
            room_description=room.room_description,
            room_code=room.room_code,
            room_url=room.room_url,
            is_private=room.is_private,
            max_participants=room.max_participants,
            recording_enabled=room.recording_enabled,
            waiting_room_enabled=room.waiting_room_enabled,
            created_at=room.created_at,
            created_by=room.created_by,
            is_active=room.is_active,
            participants_count=participants_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения видеокомнаты {room_code}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения видеокомнаты")


@router.post("/rooms/{room_code}/join", response_model=VideoParticipantResponse)
async def join_video_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Присоединение к видеокомнате."""
    try:
        # Получаем комнату
        room_query = select(VideoRoom).where(VideoRoom.room_code == room_code)
        room_result = await db.execute(room_query)
        room = room_result.scalar_one_or_none()
        
        if not room:
            raise HTTPException(status_code=404, detail="Видеокомната не найдена")
        
        if not room.is_active:
            raise HTTPException(status_code=410, detail="Видеокомната неактивна")
        
        # Проверяем, не присоединен ли уже пользователь
        existing_participant_query = select(VideoParticipant).where(
            and_(
                VideoParticipant.room_id == room.room_id,
                VideoParticipant.user_id == current_user.user_id,
                VideoParticipant.is_online == True
            )
        )
        existing_participant_result = await db.execute(existing_participant_query)
        existing_participant = existing_participant_result.scalar_one_or_none()
        
        if existing_participant:
            raise HTTPException(status_code=400, detail="Пользователь уже в комнате")
        
        # Проверяем лимит участников
        participants_count_query = select(func.count(VideoParticipant.participant_id)).where(
            and_(
                VideoParticipant.room_id == room.room_id,
                VideoParticipant.is_online == True
            )
        )
        participants_count_result = await db.execute(participants_count_query)
        participants_count = participants_count_result.scalar()
        
        if participants_count >= room.max_participants:
            raise HTTPException(status_code=409, detail="Комната переполнена")
        
        # Создаем участника
        participant = VideoParticipant(
            room_id=room.room_id,
            user_id=current_user.user_id,
            role="participant"
        )
        
        db.add(participant)
        await db.commit()
        await db.refresh(participant)
        
        # Логируем событие
        EventLogger.log_participant_join(room.room_id, participant.participant_id, current_user.user_id)
        
        logger.info(f"Пользователь {current_user.user_id} присоединился к комнате {room.room_id}")
        
        return VideoParticipantResponse(
            participant_id=participant.participant_id,
            room_id=participant.room_id,
            user_id=participant.user_id,
            user_name=current_user.user_full_name,
            user_avatar=current_user.user_avatar_url,
            joined_at=participant.joined_at,
            is_online=participant.is_online,
            is_muted=participant.is_muted,
            is_video_enabled=participant.is_video_enabled,
            is_screen_sharing=participant.is_screen_sharing,
            role=participant.role,
            permissions=participant.permissions,
            last_activity=participant.last_activity
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка присоединения к комнате: {e}")
        raise HTTPException(status_code=500, detail="Ошибка присоединения к комнате")


@router.delete("/rooms/{room_code}/leave")
async def leave_video_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Выход из видеокомнаты."""
    try:
        # Получаем комнату
        room_query = select(VideoRoom).where(VideoRoom.room_code == room_code)
        room_result = await db.execute(room_query)
        room = room_result.scalar_one_or_none()
        
        if not room:
            raise HTTPException(status_code=404, detail="Видеокомната не найдена")
        
        # Получаем участника
        participant_query = select(VideoParticipant).where(
            and_(
                VideoParticipant.room_id == room.room_id,
                VideoParticipant.user_id == current_user.user_id,
                VideoParticipant.is_online == True
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()
        
        if not participant:
            raise HTTPException(status_code=404, detail="Пользователь не найден в комнате")
        
        # Обновляем статус участника
        participant.is_online = False
        participant.left_at = func.now()
        
        await db.commit()
        
        # Логируем событие
        EventLogger.log_participant_leave(room.room_id, participant.participant_id, current_user.user_id)
        
        logger.info(f"Пользователь {current_user.user_id} покинул комнату {room.room_id}")
        
        return {"message": "Пользователь покинул комнату"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка выхода из комнаты: {e}")
        raise HTTPException(status_code=500, detail="Ошибка выхода из комнаты")


# ==================== PARTICIPANTS ====================

@router.get("/rooms/{room_code}/participants", response_model=List[VideoParticipantResponse])
async def get_room_participants(
    room_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка участников комнаты."""
    try:
        # Получаем комнату
        room_query = select(VideoRoom).where(VideoRoom.room_code == room_code)
        room_result = await db.execute(room_query)
        room = room_result.scalar_one_or_none()
        
        if not room:
            raise HTTPException(status_code=404, detail="Видеокомната не найдена")
        
        # Проверяем, что пользователь участник комнаты
        participant_query = select(VideoParticipant).where(
            and_(
                VideoParticipant.room_id == room.room_id,
                VideoParticipant.user_id == current_user.user_id
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()
        
        if not participant:
            raise HTTPException(status_code=403, detail="Доступ запрещен")
        
        # Получаем участников
        query = select(VideoParticipant).options(
            joinedload(VideoParticipant.user)
        ).where(VideoParticipant.room_id == room.room_id)
        
        result = await db.execute(query)
        participants = result.scalars().all()
        
        # Формируем ответ
        response = []
        for participant in participants:
            response.append(VideoParticipantResponse(
                participant_id=participant.participant_id,
                room_id=participant.room_id,
                user_id=participant.user_id,
                user_name=participant.user.user_full_name if participant.user else None,
                user_avatar=participant.user.user_avatar_url if participant.user else None,
                joined_at=participant.joined_at,
                left_at=participant.left_at,
                is_online=participant.is_online,
                is_muted=participant.is_muted,
                is_video_enabled=participant.is_video_enabled,
                is_screen_sharing=participant.is_screen_sharing,
                role=participant.role,
                permissions=participant.permissions,
                last_activity=participant.last_activity
            ))
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения участников: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения участников")


# ==================== WEBSOCKET ====================

@router.websocket("/ws/{room_code}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, user_id: int):
    """WebSocket endpoint для видеоконференции."""
    await websocket.accept()
    
    try:
        # Получаем информацию о комнате
        async with get_db() as db:
            room_query = select(VideoRoom).where(VideoRoom.room_code == room_code)
            room_result = await db.execute(room_query)
            room = room_result.scalar_one_or_none()
            
            if not room:
                await websocket.close(code=1008, reason="Room not found")
                return
            
            # Получаем информацию об участнике
            participant_query = select(VideoParticipant).where(
                and_(
                    VideoParticipant.room_id == room.room_id,
                    VideoParticipant.user_id == user_id
                )
            )
            participant_result = await db.execute(participant_query)
            participant = participant_result.scalar_one_or_none()
            
            if not participant:
                await websocket.close(code=1008, reason="Participant not found")
                return
        
        # Создаем WebRTC соединение
        connection_id = f"{room_code}_{user_id}"
        participant_data = {
            'user_id': user_id,
            'room_id': room.room_id,
            'role': participant.role
        }
        
        pc = await webrtc_manager.create_connection(connection_id, room.room_id, participant_data)
        
        while True:
            # Получаем сообщение
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Обрабатываем WebRTC сигналы
            if message.get('type') == 'offer':
                answer = await webrtc_manager.handle_offer(connection_id, message['data'])
                await websocket.send_text(json.dumps({
                    'type': 'answer',
                    'data': answer
                }))
            
            elif message.get('type') == 'answer':
                await webrtc_manager.handle_answer(connection_id, message['data'])
            
            elif message.get('type') == 'ice-candidate':
                await webrtc_manager.handle_ice_candidate(connection_id, message['data'])
            
            elif message.get('type') == 'mute-audio':
                await webrtc_manager.mute_audio(connection_id, message['data']['muted'])
            
            elif message.get('type') == 'mute-video':
                await webrtc_manager.mute_video(connection_id, message['data']['muted'])
            
            elif message.get('type') == 'start-screen-share':
                # Создаем трек для демонстрации экрана
                screen_track = MediaTrackFactory.create_screen_track()
                await webrtc_manager.start_screen_share(connection_id, screen_track)
            
            elif message.get('type') == 'stop-screen-share':
                await webrtc_manager.stop_screen_share(connection_id)
            
            elif message.get('type') == 'ping':
                await websocket.send_text(json.dumps({'type': 'pong'}))
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket соединение закрыто для пользователя {user_id} в комнате {room_code}")
    except Exception as e:
        logger.error(f"Ошибка WebSocket соединения: {e}")
        await websocket.close(code=1011, reason="Internal error")
