from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import json
from datetime import datetime

from src.db.database import get_db
from src.auth.auth import get_current_user
from src.db.models import User, VideoRoom, VideoParticipant
from src.video.service import VideoService
from src.video.manager import manager
from src.video.recording import recording_manager
from src.video.schemas import (
    VideoRoomCreate, VideoRoomResponse, RoomInvitationCreate,
    JoinRoomRequest, WebRTCSignal
)
from src.core.config_log import logger

router = APIRouter(prefix="/video", tags=["video"])


# Демо маршруты без авторизации (in-memory)
demo_rooms = {}  # Хранилище демо комнат в памяти

@router.post("/demo/rooms")
async def create_demo_room(room_data: VideoRoomCreate):
    """Создание демо комнаты без авторизации (in-memory)"""
    try:
        import uuid
        from datetime import datetime
        
        room_id = len(demo_rooms) + 1
        room_code = room_data.room_code or f"DEMO{room_id:04d}"
        
        # Создаем демо комнату в памяти
        demo_room = {
            "room_id": room_id,
            "room_name": room_data.room_name,
            "room_description": room_data.room_description,
            "room_code": room_code,
            "room_url": f"/room/{room_code}",
            "created_at": datetime.now().isoformat(),
            "created_by": 999999,
            "is_active": True,
            "is_private": room_data.is_private,
            "max_participants": room_data.max_participants,
            "recording_enabled": room_data.recording_enabled,
            "waiting_room_enabled": room_data.waiting_room_enabled
        }
        
        demo_rooms[room_code] = demo_room
        logger.info(f"Создана демо видеокомната {room_id} с кодом {room_code}")
        return demo_room
    except Exception as e:
        logger.error(f"Ошибка создания демо комнаты: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка создания демо комнаты"
        )


@router.get("/demo/rooms/{room_code}")
async def get_demo_room_info(room_code: str):
    """Получение информации о демо комнате (in-memory)"""
    try:
        if room_code not in demo_rooms:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Комната не найдена"
            )
        
        room = demo_rooms[room_code]
        
        return {
            "room": room,
            "participants": [],  # Для демо пока пустой список
            "online_count": 0
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения информации о демо комнате: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка получения информации о комнате"
        )


@router.post("/rooms", response_model=VideoRoomResponse)
async def create_video_room(
    room_data: VideoRoomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создание новой видеокомнаты"""
    try:
        video_service = VideoService(db)
        room = await video_service.create_room(room_data, current_user.user_id)
        logger.info(f"Создана видеокомната {room.room_id} пользователем {current_user.user_id}")
        return room
    except Exception as e:
        logger.error(f"Ошибка создания видеокомнаты: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка создания видеокомнаты"
        )


@router.post("/rooms/join", response_model=VideoRoomResponse)
async def join_video_room(
    join_data: JoinRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Присоединение к видеокомнате"""
    video_service = VideoService(db)
    room = await video_service.join_room(join_data.room_code, current_user.user_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Комната не найдена или неактивна"
        )
    
    return room


@router.get("/rooms", response_model=List[VideoRoomResponse])
async def get_user_rooms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка комнат пользователя"""
    video_service = VideoService(db)
    rooms = await video_service.get_user_rooms(current_user.user_id)
    return rooms


@router.get("/rooms/{room_code}")
async def get_room_info(
    room_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о комнате"""
    video_service = VideoService(db)
    room = await video_service.get_room_by_code(room_code)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Комната не найдена"
        )
    
    participants = await video_service.get_room_participants(room.room_id)
    
    return {
        "room": room,
        "participants": participants,
        "online_count": len(participants)
    }


@router.websocket("/ws/{room_code}")
async def video_websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    user_id: str = Query(None)
):
    """WebSocket endpoint для видеоконференции"""
    # Получаем user_id из query параметров
    if not user_id:
        # Если user_id не передан, генерируем случайный
        import random
        user_id = f"user_{random.randint(1000, 9999)}"
    
    user_name = f"User {user_id}"
    
    try:
        await manager.connect(websocket, room_code, user_id, user_name)
        logger.info(f"WebSocket подключен: комната={room_code}, пользователь={user_id}")
    
        while True:
            try:
                # Ожидаем сообщения от клиента
                data = await websocket.receive_json()
                message_type = data.get("type")
                
                logger.debug(f"Получено сообщение: {message_type} от пользователя {user_id}")
            
                if message_type == "webrtc_signal":
                    await manager.handle_webrtc_signal(data, room_code, websocket)
            
                elif message_type == "chat_message":
                    await manager.handle_chat_message(data, room_code, websocket)
                
                elif message_type == "user_action":
                    await manager.handle_user_action(data, room_code, websocket)
                
                elif message_type == "recording_control":
                    await manager.handle_recording_control(data, room_code, websocket)
            
                elif message_type == "media_stream_event":
                    await manager.handle_media_stream_event(data, room_code, websocket)
            
                elif message_type == "ping":
                    # Ответ на ping для поддержания соединения
                    await manager.send_personal_message({"type": "pong"}, websocket)
                
                elif message_type == "user_info":
                    # Обновляем информацию о пользователе
                    user_name = data.get("user_name", f"User {user_id}")
                    if user_id in manager.user_info:
                        manager.user_info[user_id]["user_name"] = user_name
                    logger.info(f"Обновлена информация пользователя {user_id}: {user_name}")
                
                elif message_type == "get_room_stats":
                    # Отправляем статистику комнаты
                    await manager.send_room_stats(room_code)
                
                elif message_type == "get_participants":
                    # Отправляем список участников
                    participants = manager.get_room_participants(room_code)
                    await manager.send_personal_message({
                        "type": "participants_list",
                        "participants": participants,
                        "your_id": user_id,
                        "room_id": room_code
                    }, websocket)
                
                else:
                    logger.warning(f"Неизвестный тип сообщения: {message_type}")
                    
            except Exception as e:
                logger.error(f"Ошибка обработки сообщения: {e}")
                break
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket отключен: комната={room_code}, пользователь={user_id}")
        manager.disconnect(websocket, room_code, user_id)
        
        # Уведомляем других участников о выходе
        leave_message = {
            "type": "user_left",
            "user_id": user_id,
            "user_name": user_name,
            "room_id": room_code,
            "timestamp": datetime.now().isoformat(),
            "participants_count": len(manager.get_room_participants(room_code))
        }
        await manager.broadcast_to_room(leave_message, room_code)
    
    except Exception as e:
        logger.error(f"Ошибка WebSocket: {e}")
        manager.disconnect(websocket, room_code, user_id)


@router.get("/rooms/{room_id}/stats")
async def get_room_statistics(
    room_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение статистики комнаты"""
    try:
        video_service = VideoService(db)
        stats = await video_service.get_room_statistics(room_id)
        return stats
    except Exception as e:
        logger.error(f"Ошибка получения статистики комнаты: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка получения статистики"
        )


@router.post("/rooms/{room_id}/invite")
async def invite_to_room(
    room_id: int,
    invitation_data: RoomInvitationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Приглашение пользователя в комнату"""
    try:
        video_service = VideoService(db)
        invitation = await video_service.create_invitation(room_id, invitation_data, current_user.user_id)
        return {
            "invitation_id": invitation.invitation_id,
            "invitation_code": invitation.invitation_code,
            "expires_at": invitation.expires_at.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка создания приглашения: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка создания приглашения"
        )


@router.post("/rooms/join-by-invitation/{invitation_code}")
async def join_by_invitation(
    invitation_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Присоединение к комнате по приглашению"""
    try:
        video_service = VideoService(db)
        # Здесь нужно добавить логику проверки приглашения
        # Пока что возвращаем ошибку
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Функция присоединения по приглашению в разработке"
        )
    except Exception as e:
        logger.error(f"Ошибка присоединения по приглашению: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка присоединения по приглашению"
        )


@router.delete("/rooms/{room_id}/leave")
async def leave_room(
    room_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Выход из комнаты"""
    try:
        video_service = VideoService(db)
        await video_service.leave_room(room_id, current_user.user_id)
        return {"message": "Успешно покинули комнату"}
    except Exception as e:
        logger.error(f"Ошибка выхода из комнаты: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка выхода из комнаты"
        )


@router.get("/rooms/{room_id}/participants")
async def get_room_participants(
    room_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка участников комнаты"""
    try:
        video_service = VideoService(db)
        participants = await video_service.get_room_participants(room_id)
        return {
            "room_id": room_id,
            "participants": [
                {
                    "participant_id": p.participant_id,
                    "user_id": p.user_id,
                    "user_name": p.user.user_full_name if p.user else f"User {p.user_id}",
                    "joined_at": p.joined_at.isoformat(),
                    "is_online": p.is_online,
                    "is_muted": p.is_muted,
                    "is_video_enabled": p.is_video_enabled,
                    "is_screen_sharing": p.is_screen_sharing,
                    "role": p.role
                }
                for p in participants
            ]
        }
    except Exception as e:
        logger.error(f"Ошибка получения участников: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка получения участников"
        )


# ==================== RECORDING ENDPOINTS ====================

@router.post("/rooms/{room_code}/recording/start")
async def start_recording(
    room_code: str,
    current_user: User = Depends(get_current_user)
):
    """Начало записи комнаты"""
    try:
        user_name = current_user.user_full_name or current_user.user_login
        result = await recording_manager.start_recording(room_code, str(current_user.user_id), user_name)
        
        if result["success"]:
            return {
                "success": True,
                "recording_id": result["recording_id"],
                "message": "Запись начата"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка начала записи: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка начала записи"
        )


@router.post("/rooms/{room_code}/recording/stop")
async def stop_recording(
    room_code: str,
    current_user: User = Depends(get_current_user)
):
    """Остановка записи комнаты"""
    try:
        result = await recording_manager.stop_recording(room_code, str(current_user.user_id))
        
        if result["success"]:
            return {
                "success": True,
                "recording_id": result["recording_id"],
                "message": "Запись остановлена"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка остановки записи: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка остановки записи"
        )


@router.get("/rooms/{room_code}/recording/status")
async def get_recording_status(room_code: str):
    """Получение статуса записи комнаты"""
    try:
        is_active = recording_manager.is_recording_active(room_code)
        recording_info = recording_manager.get_recording_info(room_code)
        
        return {
            "is_recording": is_active,
            "recording_info": recording_info
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса записи: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка получения статуса записи"
        )


@router.get("/recordings")
async def get_recordings_list(
    room_code: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Получение списка записей"""
    try:
        recordings = await recording_manager.get_recordings_list(room_code)
        return {
            "recordings": recordings,
            "total_count": len(recordings)
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения списка записей: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка получения списка записей"
        )


@router.get("/recordings/{recording_id}")
async def get_recording_details(
    recording_id: str,
    current_user: User = Depends(get_current_user)
):
    """Получение детальной информации о записи"""
    try:
        recording_details = await recording_manager.get_recording_details(recording_id)
        
        if not recording_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Запись не найдена"
            )
        
        return recording_details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения деталей записи: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка получения деталей записи"
        )


@router.delete("/recordings/{recording_id}")
async def delete_recording(
    recording_id: str,
    current_user: User = Depends(get_current_user)
):
    """Удаление записи"""
    try:
        success = await recording_manager.delete_recording(recording_id)
        
        if success:
            return {"message": "Запись удалена"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Запись не найдена"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления записи: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка удаления записи"
        )
