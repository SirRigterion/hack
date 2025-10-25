# src/websocket/routes.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.websocket.websocket import manager
from src.db.database import get_db
from src.core.config_log import logger

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/{room_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        room_id: str,
        token: str = Query(None, alias="token"),
        db: AsyncSession = Depends(get_db)
):
    """
    Универсальный WebSocket endpoint для чата и видео
    """
    # Аутентификация пользователя
    if not token:
        logger.warning("WebSocket: отсутствует токен")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_data = await manager.authenticate_websocket(token, db)
    if not user_data:
        logger.warning("WebSocket: невалидный токен")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Подключаем пользователя
    await manager.connect(websocket, room_id, user_data)

    try:
        # Отправляем текущему пользователю информацию о комнате
        participants = manager.get_room_participants(room_id)
        await manager.send_personal_message(
            {
                "type": "room_info",
                "room_id": room_id,
                "participants": participants,
                "your_info": {
                    "user_id": user_data["user_id"],
                    "username": user_data["username"],
                    "full_name": user_data["full_name"]
                },
                "timestamp": manager._get_timestamp()
            },
            websocket
        )

        # Основной цикл обработки сообщений
        while True:
            data = await websocket.receive_json()
            logger.debug(f"📨 WebSocket: {user_data['username']} -> {room_id}: {data.get('type')}")

            message_type = data.get("type")

            # WebRTC сигналы
            if message_type == "webrtc_offer":
                await manager.broadcast_to_room(
                    {
                        "type": "webrtc_offer",
                        "offer": data.get("offer"),
                        "sender_id": user_data["user_id"],
                        "sender_name": user_data["username"],
                        "timestamp": manager._get_timestamp()
                    },
                    room_id,
                    exclude_user_id=user_data["user_id"]
                )

            elif message_type == "webrtc_answer":
                target_user_id = data.get("target_user_id")
                if target_user_id:
                    await manager.send_to_user(
                        {
                            "type": "webrtc_answer",
                            "answer": data.get("answer"),
                            "sender_id": user_data["user_id"],
                            "sender_name": user_data["username"],
                            "timestamp": manager._get_timestamp()
                        },
                        room_id,
                        target_user_id
                    )

            elif message_type == "ice_candidate":
                target_user_id = data.get("target_user_id")
                if target_user_id:
                    await manager.send_to_user(
                        {
                            "type": "ice_candidate",
                            "candidate": data.get("candidate"),
                            "sender_id": user_data["user_id"],
                            "sender_name": user_data["username"],
                            "timestamp": manager._get_timestamp()
                        },
                        room_id,
                        target_user_id
                    )

            # ЧАТ - мгновенная доставка через WebSocket
            elif message_type == "chat_message":
                # Когда пользователь отправляет сообщение через WebSocket
                await manager.broadcast_to_room(
                    {
                        "type": "chat_message",
                        "data": {
                            "content": data.get("content"),
                            "sender_id": user_data["user_id"],
                            "sender_name": user_data["username"],
                            "sender_full_name": user_data["full_name"],
                            "timestamp": manager._get_timestamp(),
                            "message_id": f"ws_{user_data['user_id']}_{manager._get_timestamp()}"  # временный ID
                        },
                        "timestamp": manager._get_timestamp()
                    },
                    room_id
                    # УБИРАЕМ exclude_user_id - сообщение получают ВСЕ включая отправителя
                )

            elif message_type == "user_typing":
                await manager.broadcast_to_room(
                    {
                        "type": "user_typing",
                        "sender_id": user_data["user_id"],
                        "sender_name": user_data["username"],
                        "is_typing": data.get("is_typing", False),
                        "timestamp": manager._get_timestamp()
                    },
                    room_id,
                    exclude_user_id=user_data["user_id"]
                )

            # Ping/Pong для проверки соединения
            elif message_type == "ping":
                await manager.send_personal_message(
                    {
                        "type": "pong",
                        "timestamp": data.get("timestamp")
                    },
                    websocket
                )

            # Управление медиа
            elif message_type == "media_state":
                await manager.broadcast_to_room(
                    {
                        "type": "media_state",
                        "sender_id": user_data["user_id"],
                        "video_enabled": data.get("video_enabled", True),
                        "audio_enabled": data.get("audio_enabled", True),
                        "timestamp": manager._get_timestamp()
                    },
                    room_id,
                    exclude_user_id=user_data["user_id"]
                )

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket отключен: {user_data['username']} из комнаты {room_id}")
        disconnected_user = manager.disconnect(websocket, room_id)

        if disconnected_user:
            await manager.broadcast_to_room(
                {
                    "type": "user_left",
                    "user_id": disconnected_user["user_id"],
                    "username": disconnected_user["username"],
                    "full_name": disconnected_user["full_name"],
                    "participants_count": len(manager.active_connections.get(room_id, [])),
                    "timestamp": manager._get_timestamp()
                },
                room_id
            )
    except Exception as e:
        logger.error(f"❌ Ошибка в WebSocket для {user_data['username']}: {e}")
        manager.disconnect(websocket, room_id)
