import React, { useEffect, useState, useRef } from "react";
import { ChatAPI, ChatRoomResponse, MessageResponse, MessageCreate } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const chatAPI = new ChatAPI();

export const ChatPanel: React.FC = () => {
  const [rooms, setRooms] = useState<ChatRoomResponse[]>([]);
  const [currentRoom, setCurrentRoom] = useState<ChatRoomResponse | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [newMessage, setNewMessage] = useState("");

  // --- Инициализация WS ---
  useEffect(() => {
    const initWS = async () => {
      await chatAPI.getWebsocketToken();
      if (!currentRoom) return;
    };
    initWS();
  }, [currentRoom]);

  // --- Загрузка комнат и сообщений ---
  useEffect(() => {
    const loadRooms = async () => {
      const roomsData = await chatAPI.getRooms();
      setRooms(roomsData);
      if (roomsData.length > 0) {
        handleRoomSelect(roomsData[0]);
      }
    };
    loadRooms();
  }, []);

  const loadMessages = async (roomId: number) => {
    const msgs = await chatAPI.getMessages(roomId, { limit: 50 });
    setMessages(msgs.reverse());
  };

  const handleRoomSelect = async (room: ChatRoomResponse) => {
    setCurrentRoom(room);
    await loadMessages(room.room_id);
  };

  const handleSendMessage = async () => {
    if (!currentRoom || !newMessage.trim()) return;

    const data: MessageCreate = {
      room_id: currentRoom.room_id,
      content: newMessage,
      message_type: "text",
    };

    try {
      const sentMessage = await chatAPI.sendMessage(currentRoom.room_id, data);
      setMessages((prev) => [...prev, sentMessage]);
      setNewMessage("");
    } catch (err) {
      console.error("Failed to send message:", err);
    }
  };

  return (
    <Card className="flex flex-col h-[600px] w-full max-w-4xl mx-auto">
      <CardContent className="flex flex-row h-full gap-4 p-4">
        {/* --- Список комнат --- */}
        <div className="flex flex-col w-1/4 border-r border-gray-200 overflow-y-auto">
          {rooms.map((room) => (
            <Button
              key={room.room_id}
              variant={currentRoom?.room_id === room.room_id ? "default" : "ghost"}
              className="mb-2 text-left"
              onClick={() => handleRoomSelect(room)}
            >
              {room.room_name}
            </Button>
          ))}
        </div>

        {/* --- Сообщения --- */}
        <div className="flex flex-col w-3/4 h-full">
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {messages.map((msg) => (
              <div key={msg.message_id} className="p-2 rounded-md bg-gray-100">
                <strong>{msg.sender_name ?? "Unknown"}:</strong> {msg.content}
              </div>
            ))}
          </div>

          {/* --- Ввод нового сообщения --- */}
          {currentRoom && (
            <div className="flex mt-2 gap-2">
              <Input
                className="flex-1"
                placeholder="Type a message..."
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              />
              <Button onClick={handleSendMessage}>Send</Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
