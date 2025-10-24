import enum
from typing import Optional
from datetime import datetime
from sqlalchemy import ForeignKey, String, Integer, Boolean, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import Enum as SqlEnum

from src.db.database import Base


class UserStatus(str, enum.Enum):
    REGISTERED = "registered"   # только что зарегистрирован, email не подтвержден
    ACTIVE = "active"           # email подтвержден, может входить
    BANNED = "banned"           # заблокирован админом


class User(Base):
    """
    Модель пользователя.
    """
    __tablename__ = "users"
    
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_login: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    user_full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    user_email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    user_password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    user_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False) 
    user_avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.role_id"), default=1)
    status: Mapped[UserStatus] = mapped_column(SqlEnum(UserStatus), default=UserStatus.REGISTERED, nullable=False)
    
    ban_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    banned_at:  Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    
    tokens = relationship("UserToken", back_populates="user", cascade="all, delete-orphan")
    role = relationship("Role", back_populates="users")


class UserToken(Base):
    __tablename__ = "user_tokens"

    token_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    user = relationship("User", back_populates="tokens")

class Role(Base):
    """
    Модель роли пользователя.
    """
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)

    users = relationship("User", back_populates="role")
    
# ----------------------------------------------------------------------- #
# Можно добавить UserToRoles для связи многие-ко-многим, если потребуется #
# ----------------------------------------------------------------------- #
# class UserToRoles(Base):
#     __tablename__ = "user_to_roles"

#     user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
#     role_id: Mapped[int] = mapped_column(ForeignKey("roles.role_id"), primary_key=True)

#     user = relationship("User", back_populates="roles")
#     role = relationship("Role", back_populates="users")


# ==================== CHAT MODELS ====================

class ChatRoom(Base):
    """
    Модель чат-комнаты.
    """
    __tablename__ = "chat_rooms"
    
    room_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    room_name: Mapped[str] = mapped_column(String(100), nullable=False)
    room_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Связи
    creator = relationship("User", foreign_keys=[created_by])
    participants = relationship("ChatParticipant", back_populates="room", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="room", cascade="all, delete-orphan")


class ChatParticipant(Base):
    """
    Модель участника чата.
    """
    __tablename__ = "chat_participants"
    
    participant_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("chat_rooms.room_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    
    # Связи
    room = relationship("ChatRoom", back_populates="participants")
    user = relationship("User")


class MessageStatus(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DELETED = "deleted"
    MODERATED = "moderated"


class Message(Base):
    """
    Модель сообщения в чате.
    """
    __tablename__ = "messages"
    
    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("chat_rooms.room_id"), nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    content: Mapped[str] = mapped_column(String(2000), nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text, image, file
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    status: Mapped[MessageStatus] = mapped_column(SqlEnum(MessageStatus), default=MessageStatus.SENT, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reply_to: Mapped[Optional[int]] = mapped_column(ForeignKey("messages.message_id"), nullable=True)
    
    # Связи
    room = relationship("ChatRoom", back_populates="messages")
    sender = relationship("User")
    reply_message = relationship("Message", remote_side=[message_id])
    
    # Связь для модерации
    moderation = relationship("MessageModeration", back_populates="message", uselist=False, cascade="all, delete-orphan")


class MessageModeration(Base):
    """
    Модель модерации сообщений.
    """
    __tablename__ = "message_moderation"
    
    moderation_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.message_id"), nullable=False, unique=True)
    moderator_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # approve, reject, delete
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    moderated_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)
    
    # Связи
    message = relationship("Message", back_populates="moderation")
    moderator = relationship("User")


class Notification(Base):
    """
    Модель уведомлений.
    """
    __tablename__ = "notifications"
    
    notification_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("messages.message_id"), nullable=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)  # new_message, mention, system
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)
    
    # Связи
    user = relationship("User")
    message = relationship("Message")