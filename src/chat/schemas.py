from typing import Optional, List
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


# ==================== CHAT ROOM SCHEMAS ====================

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


# ==================== MESSAGE SCHEMAS ====================

class MessageBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="Содержимое сообщения")
    message_type: MessageTypeEnum = Field(MessageTypeEnum.TEXT, description="Тип сообщения")
    reply_to: Optional[int] = Field(None, description="ID сообщения, на которое отвечаем")


class MessageCreate(MessageBase):
    room_id: int = Field(..., description="ID чат-комнаты")


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(MessageBase):
    message_id: int
    room_id: int
    sender_id: int
    sender_name: Optional[str] = None
    created_at: datetime
    edited_at: Optional[datetime] = None
    status: MessageStatusEnum
    is_deleted: bool
    reply_to: Optional[int] = None
    reply_content: Optional[str] = None
    
    class Config:
        from_attributes = True


class MessageWithModeration(MessageResponse):
    moderation: Optional[dict] = None


# ==================== PARTICIPANT SCHEMAS ====================

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
    user_avatar: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== NOTIFICATION SCHEMAS ====================

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


# ==================== MODERATION SCHEMAS ====================

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


# ==================== WEBSOCKET SCHEMAS ====================

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


# ==================== FILTER SCHEMAS ====================

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
