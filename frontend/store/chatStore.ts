// store/chatStore.ts
import { create } from "zustand";
import { MessageResponse } from "@/lib/api";

interface ChatState {
  messages: MessageResponse[];
  addMessage: (msg: MessageResponse) => void;
  setMessages: (msgs: MessageResponse[]) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
}));
