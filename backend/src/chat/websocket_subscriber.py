from src.chat.observer import chat_observer
from src.websocket.manager import manager
from src.core.config_log import logger


class WebSocketSubscriber:
    """
    Подписчик, который транслирует события в WebSocket
    """

    def __init__(self):
        self.is_registered = False

    async def handle_chat_event(self, event_type: str, data: dict):
        """Обработчик событий чата"""
        try:
            room_id = data.get('room_id')
            if not room_id:
                return

            logger.info(f"🔔 WebSocketSubscriber: событие {event_type} для комнаты {room_id}")

            if event_type == "new_message":
                # Отправляем новое сообщение через WebSocket всем участникам комнаты
                await manager.broadcast_to_room(
                    {
                        "type": "update_chat",  # Изменяем тип для принудительного обновления
                        "event": "new_message",
                        "data": data,
                        "timestamp": data.get('created_at'),
                        "message": "Новое сообщение в чате"
                    },
                    str(room_id)
                )
                logger.info(f"📢 WebSocket: сообщение {data.get('message_id')} отправлено в комнату {room_id}")

            elif event_type == "message_updated":
                await manager.broadcast_to_room(
                    {
                        "type": "update_chat",
                        "event": "message_updated",
                        "data": data,
                        "timestamp": data.get('updated_at')
                    },
                    str(room_id)
                )

            elif event_type == "message_deleted":
                await manager.broadcast_to_room(
                    {
                        "type": "update_chat",
                        "event": "message_deleted",
                        "data": data,
                        "timestamp": data.get('deleted_at')
                    },
                    str(room_id)
                )

        except Exception as e:
            logger.error(f"❌ Ошибка в WebSocketSubscriber: {e}")

    def register(self):
        """Зарегистрировать подписчика для всех комнат"""
        if not self.is_registered:
            # Подписываемся на глобальные события вместо конкретной комнаты
            # Будем обрабатывать все события с room_id
            self.is_registered = True
            logger.info("✅ WebSocketSubscriber зарегистрирован для всех комнат")


# Глобальный экземпляр подписчика
websocket_subscriber = WebSocketSubscriber()
