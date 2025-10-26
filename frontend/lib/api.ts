import axios, { AxiosInstance } from "axios";

// --- Типы ---
export interface BodyUpdateProfile {
  user_login: string | null;
  user_full_name: string | null;
  user_email: string | null;
  photo?: File | null;
}

export interface UserProfile {
  user_id: number;
  user_login: string;
  user_full_name: string;
  user_email: string;
  user_avatar_url: string | null;
  role_id: number;
  registered_at: string;
  is_deleted: boolean;
  status: "registered" | "active" | "banned";
  ban_reason: string | null;
  banned_at: string | null;
}

export interface UserLogin {
  user_indificator: string;
  user_password: string;
}

export interface UserCreate {
  user_login: string;
  user_full_name: string;
  user_email: string;
  user_password: string;
}


// --- Класс API ---
export class UserAPI {
  private axios: AxiosInstance;

  constructor(baseURL?: string) {
    this.axios = axios.create({
      baseURL: baseURL || process.env.NEXT_PUBLIC_API_URL,
      withCredentials: true,
    });
  }

  // --- User Profile ---
  async getProfile(): Promise<UserProfile> {
    const response = await this.axios.get<UserProfile>("/user/profile");
    return response.data;
  }

  async updateProfile(data: BodyUpdateProfile): Promise<UserProfile> {
    const formData = new FormData();

    if (data.user_login != null) formData.append("user_login", data.user_login);
    if (data.user_full_name != null) formData.append("user_full_name", data.user_full_name);
    if (data.user_email != null) formData.append("user_email", data.user_email);
    if (data.photo) formData.append("photo", data.photo);

    const response = await this.axios.put<UserProfile>("/user/profile", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });

    return response.data;
  }

  async deleteProfile(): Promise<void> {
    await this.axios.delete("/user/profile");
  }

  async restoreProfile(token?: string | null): Promise<void> {
    await this.axios.post("/user/profile/restore", null, {
      params: token ? { token } : {},
    });
  }

  // --- Auth ---
  async login(data: UserLogin): Promise<UserProfile> {
    const response = await this.axios.post<UserProfile>("/auth/login", data);
    return response.data;
  }

  async logout(): Promise<void> {
    await this.axios.post("/auth/logout");
  }

  async register(data: UserCreate): Promise<UserProfile> {
    const response = await this.axios.post<UserProfile>("/auth/register", data);
    return response.data;
  }

  async verifyEmail(token: string): Promise<any> {
    const response = await this.axios.get("/auth/verify-email", {
      params: { token },
    });
    return response.data;
  }

  async resendVerification(): Promise<void> {
    await this.axios.post("/auth/resend-verification");
  }

  async requestPasswordReset(): Promise<void> {
    await this.axios.post("/user/profile/reset-password/request");
  }

  async confirmPasswordReset(token: string, newPassword: string): Promise<void> {
    const body = { token, new_password: newPassword };
    await this.axios.post("/user/profile/reset-password/confirm", new URLSearchParams(body));
  }

  // --- Admin actions ---
  async promoteUser(userId: number): Promise<void> {
    await this.axios.post(`/admin/promote/${userId}`);
  }

  async setRole(userId: number, roleId: number): Promise<void> {
    await this.axios.post(`/admin/set-role/${userId}/${roleId}`);
  }

  async deleteUser(userId: number): Promise<void> {
    await this.axios.delete(`/admin/delete/${userId}`);
  }

  async restoreUser(userId: number): Promise<void> {
    await this.axios.post(`/admin/restore/${userId}`);
  }

  async banUser(userId: number, reason?: string): Promise<void> {
    await this.axios.post(`/admin/ban/${userId}`, reason ? { reason } : {});
  }

  async unbanUser(userId: number): Promise<void> {
    await this.axios.post(`/admin/unban/${userId}`);
  }

  // --- Public / Private images ---
  async getPublicImage(file: string): Promise<any> {
    const response = await this.axios.get(`/images/public/${file}`);
    return response.data;
  }

  async getPrivateImage(file: string): Promise<any> {
    const response = await this.axios.get(`/images/private/${file}`);
    return response.data;
  }
}


// --- Типы для чата ---
export interface ChatRoomCreate {
  room_name: string;
  room_description?: string | null;
  is_private?: boolean;
}

export interface ChatRoomResponse {
  room_id: number;
  room_name: string;
  room_description?: string | null;
  is_private: boolean;
  created_at: string;
  created_by: number;
  is_active: boolean;
  participants_count?: number | null;
}

export interface ChatRoomUpdate {
  room_name?: string | null;
  room_description?: string | null;
  is_private?: boolean | null;
}

export interface MessageCreate {
  room_id: number;
  content: string;
  message_type?: "text" | "image" | "file";
  reply_to?: number | null;
}

export interface MessageResponse {
  message_id: number;
  room_id: number;
  sender_id: number;
  sender_name?: string | null;
  content: string;
  message_type: "text" | "image" | "file";
  reply_to?: number | null;
  reply_content?: string | null;
  created_at: string;
  edited_at?: string | null;
  status: "sent" | "delivered" | "read" | "deleted" | "moderated";
  is_deleted: boolean;
}

export interface MessageUpdate {
  content: string;
}

export interface ChatParticipantCreate {
  room_id: number;
  user_id: number;
  is_admin?: boolean;
  is_muted?: boolean;
}

export interface ChatParticipantResponse {
  participant_id: number;
  room_id: number;
  user_id: number;
  user_name?: string | null;
  user_avatar?: string | null;
  is_admin: boolean;
  is_muted: boolean;
  joined_at: string;
  last_read_at?: string | null;
}

export interface MessageModerationCreate {
  message_id: number;
  action: string;
  reason?: string | null;
}

export interface NotificationResponse {
  notification_id: number;
  user_id: number;
  title: string;
  content: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
  related_entity_type?: string | null;
  related_entity_id?: number | null;
}

export interface ModerationHistoryResponse {
  moderation_id: number;
  message_id: number;
  moderator_id: number;
  moderator_name?: string | null;
  action: string;
  reason?: string | null;
  created_at: string;
}

export interface ModerationStatsResponse {
  total_pending: number;
  total_approved: number;
  total_rejected: number;
  total_moderated: number;
}

export interface WebsocketTokenResponse {
  token: string;
  user_id: number;
  username: string;
  full_name: string;
}

// --- Класс ChatAPI ---
export class ChatAPI {
  private axios: AxiosInstance;

  constructor(baseURL?: string) {
    this.axios = axios.create({
      baseURL: baseURL || process.env.NEXT_PUBLIC_API_URL,
      withCredentials: true,
    });
  }

  async getWebsocketToken(): Promise<WebsocketTokenResponse> {
    const response = await this.axios.get<WebsocketTokenResponse>("/ws-auth/token");
    return response.data;
  }

  // --- Chat Rooms ---
  async createRoom(data: ChatRoomCreate): Promise<ChatRoomResponse> {
    const response = await this.axios.post<ChatRoomResponse>("/chat/rooms", data);
    return response.data;
  }

  async getRooms(params?: {
    is_private?: boolean | null;
    is_active?: boolean | null;
    user_id?: number | null;
    search_text?: string | null;
    limit?: number;
    offset?: number;
  }): Promise<ChatRoomResponse[]> {
    const response = await this.axios.get<ChatRoomResponse[]>("/chat/rooms", { params });
    return response.data;
  }

  async getRoom(room_id: number): Promise<ChatRoomResponse> {
    const response = await this.axios.get<ChatRoomResponse>(`/chat/rooms/${room_id}`);
    return response.data;
  }

  async updateRoom(room_id: number, data: ChatRoomUpdate): Promise<ChatRoomResponse> {
    const response = await this.axios.put<ChatRoomResponse>(`/chat/rooms/${room_id}`, data);
    return response.data;
  }

  async joinRoom(room_id: number): Promise<void> {
    await this.axios.post(`/chat/rooms/${room_id}/join`);
  }

  // --- Messages ---
  async sendMessage(room_id: number, data: MessageCreate): Promise<MessageResponse> {
    const response = await this.axios.post<MessageResponse>(`/chat/rooms/${room_id}/messages`, data);
    return response.data;
  }

  async getMessages(room_id: number, params?: {
    sender_id?: number | null;
    message_type?: "text" | "image" | "file" | null;
    status?: "sent" | "delivered" | "read" | "deleted" | "moderated" | null;
    date_from?: string | null;
    date_to?: string | null;
    search_text?: string | null;
    limit?: number;
    offset?: number;
  }): Promise<MessageResponse[]> {
    const response = await this.axios.get<MessageResponse[]>(`/chat/rooms/${room_id}/messages`, { params });
    return response.data;
  }

  async editMessage(message_id: number, data: MessageUpdate): Promise<MessageResponse> {
    const response = await this.axios.put<MessageResponse>(`/chat/messages/${message_id}`, data);
    return response.data;
  }

  async deleteMessage(message_id: number): Promise<void> {
    await this.axios.delete(`/chat/messages/${message_id}`);
  }

  // --- Participants ---
  async addParticipant(room_id: number, data: ChatParticipantCreate): Promise<ChatParticipantResponse> {
    const response = await this.axios.post<ChatParticipantResponse>(`/chat/rooms/${room_id}/participants`, data);
    return response.data;
  }

  async getParticipants(room_id: number): Promise<ChatParticipantResponse[]> {
    const response = await this.axios.get<ChatParticipantResponse[]>(`/chat/rooms/${room_id}/participants`);
    return response.data;
  }

  // --- Notifications ---
  async getNotifications(params?: {
    limit?: number;
    offset?: number;
    unread_only?: boolean;
  }): Promise<NotificationResponse[]> {
    const response = await this.axios.get<NotificationResponse[]>("/chat/notifications", { params });
    return response.data;
  }

  async deleteNotification(notification_id: number): Promise<void> {
    await this.axios.delete(`/chat/notifications/${notification_id}`);
  }

  async getUnreadCount(): Promise<{ count: number }> {
    const response = await this.axios.get<{ count: number }>("/chat/notifications/unread-count");
    return response.data;
  }

  // --- Moderation ---
  async moderateMessage(message_id: number, data: MessageModerationCreate): Promise<void> {
    await this.axios.post(`/chat/moderation/messages/${message_id}`, data);
  }

  async getPendingMessages(params?: {
    limit?: number;
    offset?: number;
  }): Promise<MessageResponse[]> {
    const response = await this.axios.get<MessageResponse[]>("/chat/moderation/pending", { params });
    return response.data;
  }

  async getModerationHistory(params?: {
    message_id?: number | null;
    moderator_id?: number | null;
    limit?: number;
    offset?: number;
  }): Promise<ModerationHistoryResponse[]> {
    const response = await this.axios.get<ModerationHistoryResponse[]>("/chat/moderation/history", { params });
    return response.data;
  }

  async getModerationStats(): Promise<ModerationStatsResponse> {
    const response = await this.axios.get<ModerationStatsResponse>("/chat/moderation/stats");
    return response.data;
  }

  async bulkModerateMessages(params: {
    action: string;
    reason?: string | null;
  }, message_ids: number[]): Promise<void> {
    await this.axios.post("/chat/moderation/bulk", message_ids, { params });
  }
}


// --- Типы для видео API ---
export interface VideoRoomCreate {
  name: string;
  description?: string | null;
  is_private?: boolean;
}

export interface VideoRoomResponse {
  room_id: number;
  room_code: string;
  name: string;
  description?: string | null;
  is_private: boolean;
  created_at: string;
  created_by: number;
  participants_count?: number | null;
}

export interface JoinRoomRequest {
  room_code: string;
  user_name?: string;
}

export interface RoomInvitationCreate {
  user_id: number;
  message?: string;
}

export interface WebsocketTokenResponse {
  token: string;
  user_id: number;
  username: string;
  full_name: string;
}

// --- Класс VideoAPI ---
export class VideoAPI {
  private axios: AxiosInstance;

  constructor(baseURL?: string) {
    this.axios = axios.create({
      baseURL: baseURL || process.env.NEXT_PUBLIC_API_URL,
      withCredentials: true,
    });
  }

  // --- Websocket ---
  async getWebsocketToken(): Promise<WebsocketTokenResponse> {
    const response = await this.axios.get<WebsocketTokenResponse>("/ws-auth/token");
    return response.data;
  }

  // --- Demo Rooms ---
  async createDemoRoom(data: VideoRoomCreate): Promise<VideoRoomResponse> {
    const response = await this.axios.post<VideoRoomResponse>("/video/demo/rooms", data);
    return response.data;
  }

  async getDemoRoomInfo(room_code: string): Promise<VideoRoomResponse> {
    const response = await this.axios.get<VideoRoomResponse>(`/video/demo/rooms/${room_code}`);
    return response.data;
  }

  // --- User Rooms ---
  async getUserRooms(): Promise<VideoRoomResponse[]> {
    const response = await this.axios.get<VideoRoomResponse[]>("/video/rooms");
    return response.data;
  }

  async createVideoRoom(data: VideoRoomCreate): Promise<VideoRoomResponse> {
    const response = await this.axios.post<VideoRoomResponse>("/video/rooms", data);
    return response.data;
  }

  async joinVideoRoom(data: JoinRoomRequest): Promise<VideoRoomResponse> {
    const response = await this.axios.post<VideoRoomResponse>("/video/rooms/join", data);
    return response.data;
  }

  async getRoomInfo(room_code: string): Promise<VideoRoomResponse> {
    const response = await this.axios.get<VideoRoomResponse>(`/video/rooms/${room_code}`);
    return response.data;
  }

  async getRoomStatistics(room_id: number): Promise<any> {
    const response = await this.axios.get(`/video/rooms/${room_id}/stats`);
    return response.data;
  }

  async inviteToRoom(room_id: number, data: RoomInvitationCreate): Promise<void> {
    await this.axios.post(`/video/rooms/${room_id}/invite`, data);
  }

  async joinByInvitation(invitation_code: string): Promise<VideoRoomResponse> {
    const response = await this.axios.post<VideoRoomResponse>(`/video/rooms/join-by-invitation/${invitation_code}`);
    return response.data;
  }

  async leaveRoom(room_id: number): Promise<void> {
    await this.axios.delete(`/video/rooms/${room_id}/leave`);
  }

  async getRoomParticipants(room_id: number): Promise<any[]> {
    const response = await this.axios.get(`/video/rooms/${room_id}/participants`);
    return response.data;
  }

  // --- Recording ---
  async startRecording(room_code: string): Promise<void> {
    await this.axios.post(`/video/rooms/${room_code}/recording/start`);
  }

  async stopRecording(room_code: string): Promise<void> {
    await this.axios.post(`/video/rooms/${room_code}/recording/stop`);
  }

  async getRecordingStatus(room_code: string): Promise<any> {
    const response = await this.axios.get(`/video/rooms/${room_code}/recording/status`);
    return response.data;
  }

  async getRecordingsList(room_code?: string): Promise<any[]> {
    const response = await this.axios.get(`/video/recordings`, { params: { room_code } });
    return response.data;
  }

  async getRecordingDetails(recording_id: string): Promise<any> {
    const response = await this.axios.get(`/video/recordings/${recording_id}`);
    return response.data;
  }

  async deleteRecording(recording_id: string): Promise<void> {
    await this.axios.delete(`/video/recordings/${recording_id}`);
  }
}