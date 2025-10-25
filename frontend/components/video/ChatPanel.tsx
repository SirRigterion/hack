'use client';

import { useEffect, useState, useRef } from "react";
import { ChatAPI, MessageResponse } from "@/lib/api";
import { useUserStore } from "@/store/userStore";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const chatApi = new ChatAPI();

interface ChatPanelProps {
  roomId?: number; // Можно передавать id комнаты, по умолчанию 1
}

export const ChatPanel = ({ roomId = 1 }: ChatPanelProps) => {
  const user = useUserStore((state) => state.user);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [newMessage, setNewMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const fetchMessages = async () => {
    if (!user) return;
    try {
      const msgs = await chatApi.getMessages(roomId);
      setMessages(msgs);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSend = async () => {
  if (!user || !newMessage.trim()) return;
  setLoading(true);
  try {
    const msg = await chatApi.sendMessage(roomId, {
      room_id: roomId,        // добавляем обязательное поле
      content: newMessage,
    });
    setMessages((prev) => [...prev, msg]);
    setNewMessage("");
  } catch (err) {
    console.error(err);
  } finally {
    setLoading(false);
    scrollToBottom();
  }
};


  useEffect(() => {
    fetchMessages();
    const interval = setInterval(fetchMessages, 5000); // обновление каждые 5 сек
    return () => clearInterval(interval);
  }, [user, roomId]);

  useEffect(scrollToBottom, [messages]);

  if (!user) return null;

  return (
    <div className="flex flex-col h-full p-2">
      <div className="flex-1 overflow-y-auto mb-2 space-y-2">
        {messages.map((msg) => (
          <div key={msg.message_id} className="p-2 rounded border bg-gray-100">
            <strong>{msg.sender_name || "Неизвестный"}:</strong> {msg.content}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="flex gap-2">
        <Input
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Написать сообщение..."
        />
        <Button onClick={handleSend} disabled={loading}>
          {loading ? "Отправка..." : "Отправить"}
        </Button>
      </div>
    </div>
  );
};
