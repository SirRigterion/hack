from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class VideoRoomCreate(BaseModel):
    room_name: str
    room_description: Optional[str] = None
    room_code: Optional[str] = None
    is_private: bool = False
    max_participants: int = 50
    recording_enabled: bool = False
    waiting_room_enabled: bool = False


class VideoRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    room_id: int
    room_name: str
    room_description: Optional[str]
    room_code: str
    room_url: str
    created_at: datetime
    created_by: int
    is_active: bool
    is_private: bool
    max_participants: int
    recording_enabled: bool
    waiting_room_enabled: bool


class RoomInvitationCreate(BaseModel):
    invited_email: Optional[str] = None
    invited_user_id: Optional[int] = None
    expires_hours: int = 24


class WebRTCMessageType(str, Enum):
    OFFER = "offer"
    ANSWER = "answer"
    ICE_CANDIDATE = "ice_candidate"


class WebRTCSignal(BaseModel):
    type: str = "webrtc_signal"
    signal_type: WebRTCMessageType
    data: Dict[str, Any]
    target_user_id: Optional[int] = None
    sender_user_id: int


class ChatMessage(BaseModel):
    type: str = "chat_message"
    user_id: int
    username: str
    content: str


class UserAction(BaseModel):
    type: str = "user_action"
    user_id: int
    action: str  # "mute", "unmute", "video_on", "video_off", "screen_share_start", "screen_share_stop"
    value: Optional[bool] = None


class RecordingControl(BaseModel):
    type: str = "recording_control"
    action: str  # "start", "stop", "pause"
    user_id: int


class JoinRoomRequest(BaseModel):
    room_code: str
    user_id: int