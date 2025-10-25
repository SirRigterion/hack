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
      baseURL: baseURL || process.env.REACT_APP_API_URL,
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

// --- Класс ChatAPI ---
export class ChatAPI {
  private axios: AxiosInstance;

  constructor(baseURL?: string) {
    this.axios = axios.create({
      baseURL: baseURL || process.env.REACT_APP_API_URL,
      withCredentials: true,
    });
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

  async editMessage(message_id: number, content: string): Promise<MessageResponse> {
    const response = await this.axios.put<MessageResponse>(`/chat/messages/${message_id}`, { content });
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

  // --- Moderation ---
  async moderateMessage(message_id: number, action: string, reason?: string): Promise<void> {
    const body: MessageModerationCreate = { message_id, action, reason };
    await this.axios.post(`/chat/moderation/messages/${message_id}`, body);
  }

  async getPendingMessages(limit = 50, offset = 0): Promise<MessageResponse[]> {
    const response = await this.axios.get<MessageResponse[]>("/chat/moderation/pending", { params: { limit, offset } });
    return response.data;
  }
}
