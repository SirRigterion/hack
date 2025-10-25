from typing import Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User
from src.auth.auth import get_current_user  # ДОБАВЬ этот импорт
from src.video.manager import RoomManager
from src.core.config_log import logger

router = APIRouter(prefix="/video", tags=["video"])

# Менеджер комнат (синглтон)
room_manager = RoomManager()


@router.post("/rooms")
async def create_room(current_user: User = Depends(get_current_user)):
    """Создать новую комнату для видеоконференции"""
    try:
        room_id = room_manager.create_room(current_user.user_id)
        logger.info(f"Пользователь {current_user.user_id} создал комнату {room_id}")
        return {"room_id": room_id, "message": "Комната создана"}
    except Exception as e:
        logger.error(f"Ошибка создания комнаты: {e}")
        raise HTTPException(status_code=500, detail="Не удалось создать комнату")


@router.get("/rooms/{room_id}")
async def get_room_info(room_id: str, current_user: User = Depends(get_current_user)):
    """Получить информацию о комнате"""
    room = room_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    # Проверяем права доступа (можно добавить дополнительную логику)
    return {
        "room_id": room_id,
        "owner_id": room.owner_id,
        "participants": list(room.participants.keys()),
        "is_active": room.is_active
    }


@router.websocket("/ws/{room_id}")
async def websocket_video_endpoint(
        websocket: WebSocket,
        room_id: str,
        user_id: Optional[int] = None
):
    """WebSocket endpoint для видео-звонков"""
    await websocket.accept()

    try:
        # Добавляем пользователя в комнату
        await room_manager.connect_user(room_id, user_id, websocket)

        while True:
            # Ожидаем сообщения от клиента
            data = await websocket.receive_json()

            # Обрабатываем разные типы сообщений
            message_type = data.get("type")

            if message_type == "offer":
                # Пересылаем offer другим участникам
                await room_manager.broadcast_to_room(
                    room_id,
                    {"type": "offer", "data": data["data"]},
                    exclude_user=user_id
                )

            elif message_type == "answer":
                # Пересылаем answer другим участникам
                await room_manager.broadcast_to_room(
                    room_id,
                    {"type": "answer", "data": data["data"]},
                    exclude_user=user_id
                )

            elif message_type == "ice-candidate":
                # Пересылаем ICE candidate другим участникам
                await room_manager.broadcast_to_room(
                    room_id,
                    {"type": "ice-candidate", "data": data["data"]},
                    exclude_user=user_id
                )

            elif message_type == "chat":
                # Обработка текстовых сообщений в чате
                await room_manager.broadcast_to_room(
                    room_id,
                    {"type": "chat", "user": user_id, "message": data["message"]}
                )

    except WebSocketDisconnect:
        logger.info(f"Пользователь {user_id} отключился от комнаты {room_id}")
        room_manager.disconnect_user(room_id, user_id)
    except Exception as e:
        logger.error(f"Ошибка в WebSocket видео: {e}")
        room_manager.disconnect_user(room_id, user_id)


@router.delete("/rooms/{room_id}")
async def delete_room(room_id: str, current_user: User = Depends(get_current_user)):
    """Удалить комнату (только владелец)"""
    room = room_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    if room.owner_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Недостаточно прав для удаления комнаты")

    room_manager.delete_room(room_id)
    logger.info(f"Пользователь {current_user.user_id} удалил комнату {room_id}")

    return {"message": "Комната удалена"}


@router.get("/rooms")
async def list_rooms(current_user: User = Depends(get_current_user)):
    """Получить список активных комнат"""
    rooms = room_manager.get_active_rooms()
    return {"rooms": rooms}