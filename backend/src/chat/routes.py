from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

from src.db.database import get_db
from src.db.models import (
    User, ChatRoom, ChatParticipant, Message, MessageStatus
)
from src.chat.schemas import (
    ChatRoomCreate, ChatRoomUpdate, ChatRoomResponse,
    MessageCreate, MessageUpdate, MessageResponse,
    ChatParticipantCreate, ChatParticipantResponse,
    MessageModerationCreate, MessageModerationResponse,
    MessageFilter, ChatRoomFilter, NotificationResponse
)
from src.websocket.manager import manager
from src.auth.auth import get_current_user
from src.core.config_log import logger

# В начале файла routes.py, после импортов
from src.chat.observer import chat_observer
from src.chat.websocket_subscriber import websocket_subscriber

# Заменяем существующую регистрацию на:
# Регистрируем WebSocket подписчик как глобальный обработчик
chat_observer.subscribe_global(websocket_subscriber.handle_chat_event)
logger.info("✅ WebSocket подписчик зарегистрирован как глобальный обработчик событий чата")

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/rooms", response_model=ChatRoomResponse)
async def create_chat_room(
        room_data: ChatRoomCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Создание новой чат-комнаты."""
    try:
        # Создаем комнату
        room = ChatRoom(
            room_name=room_data.room_name,
            room_description=room_data.room_description,
            is_private=room_data.is_private,
            created_by=current_user.user_id
        )

        try:
            db.add(room)
            await db.flush()  # Получаем room_id

            # Добавляем создателя как участника
            participant = ChatParticipant(
                room_id=room.room_id,
                user_id=current_user.user_id,
                is_admin=True
            )

            db.add(participant)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка создания чат-комнаты: {e}")
            raise HTTPException(status_code=500, detail="Ошибка создания чат-комнаты")
        await db.refresh(room)

        logger.info(f"Создана чат-комната {room.room_id} пользователем {current_user.user_id}")

        return ChatRoomResponse(
            room_id=room.room_id,
            room_name=room.room_name,
            room_description=room.room_description,
            is_private=room.is_private,
            created_at=room.created_at,
            created_by=room.created_by,
            is_active=room.is_active
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка создания чат-комнаты: {e}")
        raise HTTPException(status_code=500, detail="Ошибка создания чат-комнаты")


@router.get("/rooms", response_model=List[ChatRoomResponse])
async def get_chat_rooms(
        filter_params: ChatRoomFilter = Depends(),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение списка чат-комнат."""
    try:
        # Базовый запрос
        query = select(ChatRoom).options(selectinload(ChatRoom.participants))

        # Фильтры
        if filter_params.is_private is not None:
            query = query.where(ChatRoom.is_private == filter_params.is_private)

        if filter_params.is_active is not None:
            query = query.where(ChatRoom.is_active == filter_params.is_active)

        if filter_params.search_text:
            query = query.where(
                or_(
                    ChatRoom.room_name.ilike(f"%{filter_params.search_text}%"),
                    ChatRoom.room_description.ilike(f"%{filter_params.search_text}%")
                )
            )

        # Если указан user_id, показываем только комнаты, где пользователь участник
        if filter_params.user_id:
            query = query.join(ChatParticipant).where(
                and_(
                    ChatParticipant.user_id == filter_params.user_id,
                    ChatParticipant.room_id == ChatRoom.room_id
                )
            )

        # Пагинация
        query = query.offset(filter_params.offset).limit(filter_params.limit)

        result = await db.execute(query)
        rooms = result.scalars().all()

        # Формируем ответ
        response = []
        for room in rooms:
            participants_count = len(room.participants)
            response.append(ChatRoomResponse(
                room_id=room.room_id,
                room_name=room.room_name,
                room_description=room.room_description,
                is_private=room.is_private,
                created_at=room.created_at,
                created_by=room.created_by,
                is_active=room.is_active,
                participants_count=participants_count
            ))

        return response

    except Exception as e:
        logger.error(f"Ошибка получения чат-комнат: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения чат-комнат")


@router.get("/rooms/{room_id}", response_model=ChatRoomResponse)
async def get_chat_room(
        room_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение информации о чат-комнате."""
    try:
        # Проверяем, что пользователь участник комнаты
        participant_query = select(ChatParticipant).where(
            and_(
                ChatParticipant.room_id == room_id,
                ChatParticipant.user_id == current_user.user_id
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        # Получаем комнату
        room_query = select(ChatRoom).where(ChatRoom.room_id == room_id)
        room_result = await db.execute(room_query)
        room = room_result.scalar_one_or_none()

        if not room:
            raise HTTPException(status_code=404, detail="Чат-комната не найдена")

        # Получаем количество участников
        count_query = select(func.count(ChatParticipant.participant_id)).where(
            ChatParticipant.room_id == room_id
        )
        count_result = await db.execute(count_query)
        participants_count = count_result.scalar()

        return ChatRoomResponse(
            room_id=room.room_id,
            room_name=room.room_name,
            room_description=room.room_description,
            is_private=room.is_private,
            created_at=room.created_at,
            created_by=room.created_by,
            is_active=room.is_active,
            participants_count=participants_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения чат-комнаты {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения чат-комнаты")


@router.put("/rooms/{room_id}", response_model=ChatRoomResponse)
async def update_chat_room(
        room_id: int,
        room_data: ChatRoomUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Обновление чат-комнаты."""
    try:
        # Проверяем права доступа
        participant_query = select(ChatParticipant).where(
            and_(
                ChatParticipant.room_id == room_id,
                ChatParticipant.user_id == current_user.user_id,
                ChatParticipant.is_admin == True
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(status_code=403, detail="Недостаточно прав для изменения комнаты")

        # Получаем комнату
        room_query = select(ChatRoom).where(ChatRoom.room_id == room_id)
        room_result = await db.execute(room_query)
        room = room_result.scalar_one_or_none()

        if not room:
            raise HTTPException(status_code=404, detail="Чат-комната не найдена")

        # Обновляем данные
        update_data = room_data.dict(exclude_unset=True)
        if update_data:
            for field, value in update_data.items():
                setattr(room, field, value)

            await db.commit()
            await db.refresh(room)

        return ChatRoomResponse(
            room_id=room.room_id,
            room_name=room.room_name,
            room_description=room.room_description,
            is_private=room.is_private,
            created_at=room.created_at,
            created_by=room.created_by,
            is_active=room.is_active
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка обновления чат-комнаты {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обновления чат-комнаты")


@router.post("/rooms/{room_id}/messages", response_model=MessageResponse)
async def send_message(
        room_id: int,
        message_data: MessageCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Отправка сообщения в чат-комнату."""
    try:
        logger.info(f"Попытка отправки сообщения в комнату {room_id} пользователем {current_user.user_id}")

        # Проверяем, что пользователь участник комнаты
        participant_query = select(ChatParticipant).where(
            and_(
                ChatParticipant.room_id == room_id,
                ChatParticipant.user_id == current_user.user_id
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            logger.warning(f"Пользователь {current_user.user_id} не участник комнаты {room_id}")
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        if participant.is_muted:
            logger.warning(f"Пользователь {current_user.user_id} заглушен в комнате {room_id}")
            raise HTTPException(status_code=403, detail="Пользователь заглушен")

        # Валидация контента
        if not message_data.content or not message_data.content.strip():
            raise HTTPException(status_code=400, detail="Содержание сообщения не может быть пустым")

        # Валидация reply_to
        if message_data.reply_to:
            # Проверяем, что сообщение, на которое ссылаются, существует в той же комнате
            reply_message_query = select(Message).where(
                and_(
                    Message.message_id == message_data.reply_to,
                    Message.room_id == room_id
                )
            )
            reply_message_result = await db.execute(reply_message_query)
            reply_message = reply_message_result.scalar_one_or_none()

            if not reply_message:
                raise HTTPException(status_code=400, detail="Сообщение для ответа не найдено")

        # Создаем сообщение
        message = Message(
            room_id=room_id,
            sender_id=current_user.user_id,
            content=message_data.content.strip(),
            message_type=message_data.message_type.value,
            reply_to=message_data.reply_to,
            status=MessageStatus.SENT
        )

        try:
            db.add(message)
            await db.flush()

            # Автоматическая модерация (если есть)
            try:
                from src.chat.moderation import ModerationService
                moderation_service = ModerationService(db)
                moderation_result = await moderation_service.auto_moderate_message(message)
                logger.info(f"Результат модерации: {moderation_result}")
            except ImportError:
                logger.warning("Модуль модерации не найден, пропускаем модерацию")
            except Exception as e:
                logger.warning(f"Ошибка автоматической модерации: {e}")

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка отправки сообщения: {e}")
            raise HTTPException(status_code=500, detail="Ошибка отправки сообщения")
        await db.refresh(message)

        # В функции send_message, после сохранения сообщения в БД
        try:
            event_data = {
                "message_id": message.message_id,
                "room_id": room_id,
                "sender_id": current_user.user_id,
                "sender_name": current_user.user_full_name,
                "sender_login": current_user.user_login,
                "content": message.content,
                "message_type": message.message_type,
                "created_at": message.created_at.isoformat(),
                "status": message.status,
                "is_deleted": message.is_deleted,
                "reply_to": message.reply_to
            }

            # Уведомляем всех подписчиков
            await chat_observer.notify(room_id, "new_message", event_data)
            logger.info(f"🔔 Observer: новое сообщение {message.message_id} в комнате {room_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка уведомления Observer: {e}")

        try:
            from src.websocket.manager import manager

            # Формируем WebSocket сообщение
            ws_message = {
                "type": "chat_message",
                "data": {
                    "message_id": message.message_id,
                    "room_id": message.room_id,
                    "sender_id": message.sender_id,
                    "sender_name": current_user.user_full_name,
                    "sender_full_name": current_user.user_full_name,
                    "content": message.content,
                    "message_type": message.message_type,
                    "created_at": message.created_at.isoformat(),
                    "status": message.status,
                    "is_deleted": message.is_deleted,
                    "reply_to": message.reply_to
                },
                "timestamp": message.created_at.isoformat()
            }

            # Отправляем через WebSocket менеджер
            await manager.broadcast_to_room(ws_message, str(room_id))
            logger.info(f"📢 Сообщение {message.message_id} отправлено через WebSocket в комнату {room_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка отправки через WebSocket: {e}")

        # Получаем информацию об отправителе для ответа
        sender_query = select(User).where(User.user_id == current_user.user_id)
        sender_result = await db.execute(sender_query)
        sender = sender_result.scalar_one_or_none()

        # Формируем ответ
        response = MessageResponse(
            message_id=message.message_id,
            room_id=message.room_id,
            sender_id=message.sender_id,
            sender_name=sender.user_full_name if sender else "Неизвестный",
            content=message.content,
            message_type=message.message_type,
            created_at=message.created_at,
            edited_at=message.edited_at,
            status=message.status,
            is_deleted=message.is_deleted,
            reply_to=message.reply_to
        )

        # Отправляем через WebSocket
        try:
            await manager.broadcast_to_room(
                room_id=room_id,
                message={
                    "type": "new_message",
                    "data": response.dict()
                }
            )
            logger.info(f"Сообщение {message.message_id} отправлено через WebSocket в комнату {room_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки через WebSocket: {e}")

        logger.info(f"Успешно отправлено сообщение {message.message_id} в комнату {room_id}")

        return response

    except HTTPException as he:
        logger.error(f"HTTP ошибка при отправке сообщения: {he.detail}")
        raise he
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка отправки сообщения: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка отправки сообщения")


@router.get("/rooms/{room_id}/messages", response_model=List[MessageResponse])
async def get_messages(
        room_id: int,
        filter_params: MessageFilter = Depends(),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение сообщений чат-комнаты."""
    try:
        # Проверяем, что пользователь участник комнаты
        participant_query = select(ChatParticipant).where(
            and_(
                ChatParticipant.room_id == room_id,
                ChatParticipant.user_id == current_user.user_id
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        # Базовый запрос
        query = select(Message).options(
            joinedload(Message.sender)
        ).where(Message.room_id == room_id)

        # Фильтры
        if filter_params.sender_id:
            query = query.where(Message.sender_id == filter_params.sender_id)

        if filter_params.message_type:
            query = query.where(Message.message_type == filter_params.message_type.value)

        if filter_params.status:
            query = query.where(Message.status == filter_params.status.value)

        if filter_params.date_from:
            query = query.where(Message.created_at >= filter_params.date_from)

        if filter_params.date_to:
            query = query.where(Message.created_at <= filter_params.date_to)

        if filter_params.search_text:
            query = query.where(Message.content.ilike(f"%{filter_params.search_text}%"))

        # Сортировка по времени (новые сначала)
        query = query.order_by(Message.created_at.desc())

        # Пагинация
        query = query.offset(filter_params.offset).limit(filter_params.limit)

        result = await db.execute(query)
        messages = result.scalars().all()

        # Формируем ответ
        response = []
        for message in messages:
            response.append(MessageResponse(
                message_id=message.message_id,
                room_id=message.room_id,
                sender_id=message.sender_id,
                sender_name=message.sender.user_full_name if message.sender else None,
                content=message.content,
                message_type=message.message_type,
                created_at=message.created_at,
                edited_at=message.edited_at,
                status=message.status,
                is_deleted=message.is_deleted,
                reply_to=message.reply_to
            ))

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения сообщений: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения сообщений")


@router.put("/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
        message_id: int,
        message_data: MessageUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Редактирование сообщения."""
    try:
        # Получаем сообщение
        message_query = select(Message).where(Message.message_id == message_id)
        message_result = await db.execute(message_query)
        message = message_result.scalar_one_or_none()

        if not message:
            raise HTTPException(status_code=404, detail="Сообщение не найдено")

        # Проверяем права
        if message.sender_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Недостаточно прав для редактирования")

        # Обновляем сообщение
        message.content = message_data.content
        message.edited_at = func.now()

        await db.commit()
        await db.refresh(message)

        # Формируем ответ
        response = MessageResponse(
            message_id=message.message_id,
            room_id=message.room_id,
            sender_id=message.sender_id,
            sender_name=current_user.user_full_name,
            content=message.content,
            message_type=message.message_type,
            created_at=message.created_at,
            edited_at=message.edited_at,
            status=message.status,
            is_deleted=message.is_deleted,
            reply_to=message.reply_to
        )

        # Отправляем обновление через WebSocket
        await manager.broadcast_message(response, message.room_id)

        return response

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка редактирования сообщения {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка редактирования сообщения")


@router.delete("/messages/{message_id}")
async def delete_message(
        message_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Удаление сообщения."""
    try:
        # Получаем сообщение
        message_query = select(Message).where(Message.message_id == message_id)
        message_result = await db.execute(message_query)
        message = message_result.scalar_one_or_none()

        if not message:
            raise HTTPException(status_code=404, detail="Сообщение не найдено")

        # Проверяем права
        if message.sender_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Недостаточно прав для удаления")

        # Помечаем как удаленное
        message.is_deleted = True
        message.status = MessageStatus.DELETED

        await db.commit()

        # Отправляем уведомление через WebSocket
        response = MessageResponse(
            message_id=message.message_id,
            room_id=message.room_id,
            sender_id=message.sender_id,
            sender_name=current_user.user_full_name,
            content="Сообщение удалено",
            message_type=message.message_type,
            created_at=message.created_at,
            edited_at=message.edited_at,
            status=message.status,
            is_deleted=message.is_deleted,
            reply_to=message.reply_to
        )

        await manager.broadcast_message(response, message.room_id)

        return {"message": "Сообщение удалено"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления сообщения")


@router.post("/rooms/{room_id}/participants", response_model=ChatParticipantResponse)
async def add_participant(
        room_id: int,
        participant_data: ChatParticipantCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Добавление участника в чат-комнату."""
    try:
        # Проверяем права администратора
        admin_query = select(ChatParticipant).where(
            and_(
                ChatParticipant.room_id == room_id,
                ChatParticipant.user_id == current_user.user_id,
                ChatParticipant.is_admin == True
            )
        )
        admin_result = await db.execute(admin_query)
        admin = admin_result.scalar_one_or_none()

        if not admin:
            raise HTTPException(status_code=403, detail="Недостаточно прав для добавления участников")

        # Проверяем, что пользователь не участник
        existing_query = select(ChatParticipant).where(
            and_(
                ChatParticipant.room_id == room_id,
                ChatParticipant.user_id == participant_data.user_id
            )
        )
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()

        if existing:
            raise HTTPException(status_code=400, detail="Пользователь уже участник комнаты")

        # Добавляем участника
        participant = ChatParticipant(
            room_id=room_id,
            user_id=participant_data.user_id,
            is_admin=participant_data.is_admin,
            is_muted=participant_data.is_muted
        )

        db.add(participant)
        await db.commit()
        await db.refresh(participant)

        return ChatParticipantResponse(
            participant_id=participant.participant_id,
            room_id=participant.room_id,
            user_id=participant.user_id,
            joined_at=participant.joined_at,
            is_admin=participant.is_admin,
            is_muted=participant.is_muted,
            last_read_at=participant.last_read_at
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка добавления участника: {e}")
        raise HTTPException(status_code=500, detail="Ошибка добавления участника")


@router.get("/rooms/{room_id}/participants", response_model=List[ChatParticipantResponse])
async def get_participants(
        room_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение списка участников чат-комнаты."""
    try:
        # Проверяем, что пользователь участник комнаты
        participant_query = select(ChatParticipant).where(
            and_(
                ChatParticipant.room_id == room_id,
                ChatParticipant.user_id == current_user.user_id
            )
        )
        participant_result = await db.execute(participant_query)
        participant = participant_result.scalar_one_or_none()

        if not participant:
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        # Получаем участников
        query = select(ChatParticipant).options(
            joinedload(ChatParticipant.user)
        ).where(ChatParticipant.room_id == room_id)

        result = await db.execute(query)
        participants = result.scalars().all()

        # Формируем ответ
        response = []
        for participant in participants:
            response.append(ChatParticipantResponse(
                participant_id=participant.participant_id,
                room_id=participant.room_id,
                user_id=participant.user_id,
                user_name=participant.user.user_full_name if participant.user else None,
                user_avatar=participant.user.user_avatar_url if participant.user else None,
                joined_at=participant.joined_at,
                is_admin=participant.is_admin,
                is_muted=participant.is_muted,
                last_read_at=participant.last_read_at
            ))

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения участников: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения участников")


@router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение уведомлений пользователя."""
    try:
        from src.chat.notifications import NotificationService

        service = NotificationService(db)
        notifications = await service.get_user_notifications(
            user_id=current_user.user_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only
        )

        return notifications

    except Exception as e:
        logger.error(f"Ошибка получения уведомлений: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения уведомлений")


@router.delete("/notifications/{notification_id}")
async def delete_notification(
        notification_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Удаление уведомления."""
    try:
        from src.chat.notifications import NotificationService

        service = NotificationService(db)
        success = await service.delete_notification(notification_id, current_user.user_id)

        if not success:
            raise HTTPException(status_code=404, detail="Уведомление не найдено")

        return {"message": "Уведомление удалено"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления уведомления: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления уведомления")


@router.get("/notifications/unread-count")
async def get_unread_count(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение количества непрочитанных уведомлений."""
    try:
        from src.chat.notifications import NotificationService

        service = NotificationService(db)
        count = await service.get_unread_count(current_user.user_id)

        return {"unread_count": count}

    except Exception as e:
        logger.error(f"Ошибка получения количества непрочитанных уведомлений: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения количества уведомлений")


@router.post("/moderation/messages/{message_id}")
async def moderate_message(
        message_id: int,
        moderation_data: MessageModerationCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Модерация сообщения."""
    try:
        # Проверяем права модератора
        if current_user.role_id not in [1, 2]:  # Только админы и модераторы
            raise HTTPException(status_code=403, detail="Недостаточно прав для модерации")

        from src.chat.moderation import ModerationService

        service = ModerationService(db)
        moderation = await service.moderate_message(
            message_id=message_id,
            moderator_id=current_user.user_id,
            action=moderation_data.action,
            reason=moderation_data.reason
        )

        return MessageModerationResponse(
            moderation_id=moderation.moderation_id,
            message_id=moderation.message_id,
            moderator_id=moderation.moderator_id,
            moderator_name=current_user.user_full_name,
            action=moderation.action,
            reason=moderation.reason,
            moderated_at=moderation.moderated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка модерации сообщения {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка модерации сообщения")


@router.get("/moderation/pending", response_model=List[MessageResponse])
async def get_pending_messages(
        limit: int = 50,
        offset: int = 0,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение сообщений, ожидающих модерации."""
    try:
        # Проверяем права модератора
        if current_user.role_id not in [1, 2]:
            raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра модерации")

        from src.chat.moderation import ModerationService

        service = ModerationService(db)
        messages = await service.get_pending_messages(limit=limit, offset=offset)

        response = []
        for message in messages:
            response.append(MessageResponse(
                message_id=message.message_id,
                room_id=message.room_id,
                sender_id=message.sender_id,
                sender_name=message.sender.user_full_name if message.sender else None,
                content=message.content,
                message_type=message.message_type,
                created_at=message.created_at,
                edited_at=message.edited_at,
                status=message.status,
                is_deleted=message.is_deleted,
                reply_to=message.reply_to
            ))

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения сообщений для модерации: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения сообщений для модерации")


@router.get("/moderation/history", response_model=List[MessageModerationResponse])
async def get_moderation_history(
        message_id: Optional[int] = None,
        moderator_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение истории модерации."""
    try:
        # Проверяем права модератора
        if current_user.role_id not in [1, 2]:
            raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра истории модерации")

        from src.chat.moderation import ModerationService

        service = ModerationService(db)
        history = await service.get_moderation_history(
            message_id=message_id,
            moderator_id=moderator_id,
            limit=limit,
            offset=offset
        )

        return history

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения истории модерации: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения истории модерации")


@router.get("/moderation/stats")
async def get_moderation_stats(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение статистики модерации."""
    try:
        # Проверяем права модератора
        if current_user.role_id not in [1, 2]:
            raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра статистики")

        from src.chat.moderation import ModerationService

        service = ModerationService(db)
        stats = await service.get_moderation_stats()

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения статистики модерации: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения статистики модерации")


@router.post("/moderation/bulk")
async def bulk_moderate_messages(
        message_ids: List[int],
        action: str,
        reason: Optional[str] = None,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Массовая модерация сообщений."""
    try:
        # Проверяем права модератора
        if current_user.role_id not in [1, 2]:
            raise HTTPException(status_code=403, detail="Недостаточно прав для массовой модерации")

        from src.chat.moderation import ModerationService

        service = ModerationService(db)
        moderated_count = await service.bulk_moderate_messages(
            message_ids=message_ids,
            moderator_id=current_user.user_id,
            action=action,
            reason=reason
        )

        return {
            "message": f"Отмодерировано {moderated_count} из {len(message_ids)} сообщений",
            "moderated_count": moderated_count,
            "total_count": len(message_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка массовой модерации: {e}")
        raise HTTPException(status_code=500, detail="Ошибка массовой модерации")


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """WebSocket endpoint для чата."""
    try:
        handler = WebSocketHandler(manager)
        await handler.handle_connection(websocket, user_id)
    except WebSocketDisconnect:
        logger.info(f"WebSocket отключен для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка WebSocket чата: {e}")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except:
            pass
