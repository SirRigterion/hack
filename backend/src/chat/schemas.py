from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class MessageStatusEnum(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DELETED = "deleted"
    MODERATED = "moderated"


class MessageTypeEnum(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"


class NotificationTypeEnum(str, Enum):
    NEW_MESSAGE = "new_message"
    MENTION = "mention"
    SYSTEM = "system"


class ChatRoomBase(BaseModel):
    room_name: str = Field(..., min_length=1, max_length=100, description="Название чат-комнаты")
    room_description: Optional[str] = Field(None, max_length=500, description="Описание чат-комнаты")
    is_private: bool = Field(False, description="Приватная ли комната")


class ChatRoomCreate(ChatRoomBase):
    pass


class ChatRoomUpdate(BaseModel):
    room_name: Optional[str] = Field(None, min_length=1, max_length=100)
    room_description: Optional[str] = Field(None, max_length=500)
    is_private: Optional[bool] = None


class ChatRoomResponse(ChatRoomBase):
    room_id: int
    created_at: datetime
    created_by: int
    is_active: bool
    participants_count: Optional[int] = None

    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="Содержимое сообщения")
    message_type: MessageTypeEnum = Field(MessageTypeEnum.TEXT, description="Тип сообщения")
    reply_to: Optional[int] = Field(None, ge=1, description="ID сообщения, на которое отвечаем")

    def __init__(self, **data):
        # Преобразуем 0 в None для reply_to
        if 'reply_to' in data and data['reply_to'] == 0:
            data['reply_to'] = None
        super().__init__(**data)


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(MessageBase):
    message_id: int
    room_id: int
    sender_id: int
    sender_name: Optional[str] = None
    sender_full_name: Optional[str] = None  # Добавлено для фронтенда
    content: str
    message_type: str
    created_at: datetime
    edited_at: Optional[datetime] = None
    status: str
    is_deleted: bool
    reply_to: Optional[int] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class MessageWithModeration(MessageResponse):
    moderation: Optional[dict] = None


class ChatParticipantBase(BaseModel):
    user_id: int = Field(..., description="ID пользователя")
    is_admin: bool = Field(False, description="Администратор ли чата")
    is_muted: bool = Field(False, description="Заглушен ли пользователь")


class ChatParticipantCreate(ChatParticipantBase):
    room_id: int = Field(..., description="ID чат-комнаты")


class ChatParticipantUpdate(BaseModel):
    is_admin: Optional[bool] = None
    is_muted: Optional[bool] = None


class ChatParticipantResponse(ChatParticipantBase):
    participant_id: int
    room_id: int
    joined_at: datetime
    last_read_at: Optional[datetime] = None
    user_name: Optional[str] = None
    user_full_name: Optional[str] = None  # Добавлено для фронтенда
    user_avatar: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationBase(BaseModel):
    notification_type: NotificationTypeEnum = Field(..., description="Тип уведомления")
    title: str = Field(..., min_length=1, max_length=200, description="Заголовок уведомления")
    content: str = Field(..., min_length=1, max_length=500, description="Содержимое уведомления")


class NotificationCreate(NotificationBase):
    user_id: int = Field(..., description="ID пользователя")
    message_id: Optional[int] = Field(None, description="ID сообщения")


class NotificationResponse(NotificationBase):
    notification_id: int
    user_id: int
    message_id: Optional[int] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MessageModerationBase(BaseModel):
    action: str = Field(..., description="Действие модерации")
    reason: Optional[str] = Field(None, max_length=500, description="Причина модерации")


class MessageModerationCreate(MessageModerationBase):
    message_id: int = Field(..., description="ID сообщения")


class MessageModerationResponse(MessageModerationBase):
    moderation_id: int
    message_id: int
    moderator_id: int
    moderator_name: Optional[str] = None
    moderated_at: datetime

    class Config:
        from_attributes = True


class WebSocketMessage(BaseModel):
    type: str = Field(..., description="Тип WebSocket сообщения")
    data: dict = Field(..., description="Данные сообщения")


class ChatMessageWebSocket(WebSocketMessage):
    type: str = Field("chat_message", description="Тип сообщения чата")
    data: MessageResponse = Field(..., description="Данные сообщения")


class UserTypingWebSocket(WebSocketMessage):
    type: str = Field("user_typing", description="Пользователь печатает")
    data: dict = Field(..., description="Данные о печатающем пользователе")


class UserOnlineWebSocket(WebSocketMessage):
    type: str = Field("user_online", description="Пользователь онлайн")
    data: dict = Field(..., description="Данные о пользователе")


# ДОБАВЛЕНЫ НОВЫЕ СХЕМЫ ДЛЯ СИНХРОНИЗАЦИИ

class RoomStateWebSocket(WebSocketMessage):
    type: str = Field("room_state_update", description="Обновление состояния комнаты")
    data: dict = Field(..., description="Данные состояния комнаты")


class SyncRequiredWebSocket(WebSocketMessage):
    type: str = Field("sync_required", description="Требуется синхронизация")
    data: dict = Field(..., description="Данные для синхронизации")


class ForceSyncWebSocket(WebSocketMessage):
    type: str = Field("force_sync", description="Принудительная синхронизация")
    data: dict = Field(..., description="Данные синхронизации")


class MessageUpdatedWebSocket(WebSocketMessage):
    type: str = Field("message_updated", description="Сообщение обновлено")
    data: dict = Field(..., description="Данные обновленного сообщения")


class MessageDeletedWebSocket(WebSocketMessage):
    type: str = Field("message_deleted", description="Сообщение удалено")
    data: dict = Field(..., description="Данные удаленного сообщения")


class UserJoinedWebSocket(WebSocketMessage):
    type: str = Field("user_joined", description="Пользователь присоединился")
    data: dict = Field(..., description="Данные о присоединившемся пользователе")


class UserLeftWebSocket(WebSocketMessage):
    type: str = Field("user_left", description="Пользователь покинул комнату")
    data: dict = Field(..., description="Данные о покинувшем пользователе")


class RoomInfoWebSocket(WebSocketMessage):
    type: str = Field("room_info", description="Информация о комнате")
    data: dict = Field(..., description="Данные комнаты")


class MessageFilter(BaseModel):
    room_id: Optional[int] = None
    sender_id: Optional[int] = None
    message_type: Optional[MessageTypeEnum] = None
    status: Optional[MessageStatusEnum] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    search_text: Optional[str] = None
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class ChatRoomFilter(BaseModel):
    is_private: Optional[bool] = None
    is_active: Optional[bool] = None
    user_id: Optional[int] = None
    search_text: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


# ДОБАВЛЕНЫ СХЕМЫ ДЛЯ WebSocket СООБЩЕНИЙ СИНХРОНИЗАЦИИ

class WebSocketRoomState(BaseModel):
    room_id: str
    participants: List[Dict[str, Any]]
    participants_count: int
    timestamp: str


class WebSocketSyncData(BaseModel):
    room_id: int
    action: str
    timestamp: str
    data: Optional[Dict[str, Any]] = None


class WebSocketUserData(BaseModel):
    user_id: int
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    connection_type: Optional[str] = "chat"
