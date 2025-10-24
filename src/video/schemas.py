from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class ParticipantRole(str, Enum):
    HOST = "host"
    CO_HOST = "co-host"
    PARTICIPANT = "participant"


class StreamType(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN = "screen"


class QualityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    AUTO = "auto"


class EventType(str, Enum):
    JOIN = "join"
    LEAVE = "leave"
    MUTE = "mute"
    UNMUTE = "unmute"
    VIDEO_ON = "video_on"
    VIDEO_OFF = "video_off"
    SCREEN_SHARE_START = "screen_share_start"
    SCREEN_SHARE_STOP = "screen_share_stop"
    RECORDING_START = "recording_start"
    RECORDING_STOP = "recording_stop"


# ==================== VIDEO ROOM SCHEMAS ====================

class VideoRoomBase(BaseModel):
    room_name: str = Field(..., min_length=1, max_length=100, description="Название комнаты")
    room_description: Optional[str] = Field(None, max_length=500, description="Описание комнаты")
    is_private: bool = Field(False, description="Приватная ли комната")
    max_participants: int = Field(50, ge=2, le=1000, description="Максимальное количество участников")
    recording_enabled: bool = Field(False, description="Разрешена ли запись")
    waiting_room_enabled: bool = Field(False, description="Включена ли комната ожидания")


class VideoRoomCreate(VideoRoomBase):
    pass


class VideoRoomUpdate(BaseModel):
    room_name: Optional[str] = Field(None, min_length=1, max_length=100)
    room_description: Optional[str] = Field(None, max_length=500)
    is_private: Optional[bool] = None
    max_participants: Optional[int] = Field(None, ge=2, le=1000)
    recording_enabled: Optional[bool] = None
    waiting_room_enabled: Optional[bool] = None


class VideoRoomResponse(VideoRoomBase):
    room_id: int
    room_code: str
    room_url: str
    created_at: datetime
    created_by: int
    is_active: bool
    participants_count: Optional[int] = None
    current_participants: Optional[int] = None
    
    class Config:
        from_attributes = True


# ==================== PARTICIPANT SCHEMAS ====================

class VideoParticipantBase(BaseModel):
    user_id: int = Field(..., description="ID пользователя")
    role: ParticipantRole = Field(ParticipantRole.PARTICIPANT, description="Роль участника")
    permissions: Optional[Dict[str, Any]] = Field(None, description="Права участника")


class VideoParticipantCreate(VideoParticipantBase):
    room_id: int = Field(..., description="ID комнаты")


class VideoParticipantUpdate(BaseModel):
    role: Optional[ParticipantRole] = None
    permissions: Optional[Dict[str, Any]] = None
    is_muted: Optional[bool] = None
    is_video_enabled: Optional[bool] = None


class VideoParticipantResponse(VideoParticipantBase):
    participant_id: int
    room_id: int
    joined_at: datetime
    left_at: Optional[datetime] = None
    is_online: bool
    is_muted: bool
    is_video_enabled: bool
    is_screen_sharing: bool
    last_activity: Optional[datetime] = None
    user_name: Optional[str] = None
    user_avatar: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== MEDIA STREAM SCHEMAS ====================

class MediaStreamBase(BaseModel):
    stream_type: StreamType = Field(..., description="Тип потока")
    quality: QualityLevel = Field(QualityLevel.AUTO, description="Качество потока")
    bitrate: Optional[int] = Field(None, ge=100, le=10000, description="Битрейт")
    resolution: Optional[str] = Field(None, description="Разрешение")


class MediaStreamCreate(MediaStreamBase):
    room_id: int = Field(..., description="ID комнаты")
    participant_id: int = Field(..., description="ID участника")
    stream_id_webrtc: str = Field(..., description="WebRTC ID потока")


class MediaStreamUpdate(BaseModel):
    is_active: Optional[bool] = None
    quality: Optional[QualityLevel] = None
    bitrate: Optional[int] = Field(None, ge=100, le=10000)
    resolution: Optional[str] = None


class MediaStreamResponse(MediaStreamBase):
    stream_id: int
    room_id: int
    participant_id: int
    stream_id_webrtc: str
    is_active: bool
    created_at: datetime
    ended_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ==================== RECORDING SCHEMAS ====================

class RoomRecordingBase(BaseModel):
    room_id: int = Field(..., description="ID комнаты")


class RoomRecordingCreate(RoomRecordingBase):
    pass


class RoomRecordingResponse(RoomRecordingBase):
    recording_id: int
    started_by: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[int] = None
    is_processing: bool
    is_available: bool
    thumbnail_path: Optional[str] = None
    starter_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== INVITATION SCHEMAS ====================

class RoomInvitationBase(BaseModel):
    room_id: int = Field(..., description="ID комнаты")
    invited_user_id: Optional[int] = Field(None, description="ID приглашенного пользователя")
    invited_email: Optional[str] = Field(None, description="Email приглашенного пользователя")
    expires_in_hours: int = Field(24, ge=1, le=168, description="Срок действия в часах")


class RoomInvitationCreate(RoomInvitationBase):
    pass


class RoomInvitationResponse(RoomInvitationBase):
    invitation_id: int
    invited_by: int
    invitation_code: str
    expires_at: datetime
    is_used: bool
    used_at: Optional[datetime] = None
    created_at: datetime
    inviter_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== EVENT SCHEMAS ====================

class RoomEventBase(BaseModel):
    event_type: EventType = Field(..., description="Тип события")
    event_data: Optional[Dict[str, Any]] = Field(None, description="Данные события")


class RoomEventCreate(RoomEventBase):
    room_id: int = Field(..., description="ID комнаты")
    participant_id: Optional[int] = Field(None, description="ID участника")


class RoomEventResponse(RoomEventBase):
    event_id: int
    room_id: int
    participant_id: Optional[int] = None
    created_at: datetime
    participant_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== WEBSOCKET SCHEMAS ====================

class WebRTCSignal(BaseModel):
    type: str = Field(..., description="Тип сигнала")
    data: Dict[str, Any] = Field(..., description="Данные сигнала")


class ParticipantStatusUpdate(BaseModel):
    participant_id: int
    is_online: bool
    is_muted: bool
    is_video_enabled: bool
    is_screen_sharing: bool


class RoomStatusUpdate(BaseModel):
    room_id: int
    participants_count: int
    is_recording: bool
    active_streams: List[int]


# ==================== FILTER SCHEMAS ====================

class VideoRoomFilter(BaseModel):
    is_private: Optional[bool] = None
    is_active: Optional[bool] = None
    created_by: Optional[int] = None
    search_text: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class ParticipantFilter(BaseModel):
    room_id: Optional[int] = None
    role: Optional[ParticipantRole] = None
    is_online: Optional[bool] = None
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class RecordingFilter(BaseModel):
    room_id: Optional[int] = None
    started_by: Optional[int] = None
    is_available: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


# ==================== ENCRYPTION SCHEMAS ====================

class EncryptionKey(BaseModel):
    room_id: int
    key: str
    algorithm: str = "AES-256-GCM"
    created_at: datetime


class KeyExchange(BaseModel):
    participant_id: int
    public_key: str
    encrypted_key: str
    timestamp: datetime
