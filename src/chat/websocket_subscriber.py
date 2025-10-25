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
                        "type": "chat_message",  # Оставляем стандартный тип для фронтенда
                        "data": data,
                        "timestamp": data.get('created_at'),
                        "sync_required": True  # Флаг для принудительной синхронизации
                    },
                    str(room_id)
                )
                logger.info(f"📢 WebSocket: сообщение {data.get('message_id')} отправлено в комнату {room_id}")

            elif event_type == "message_updated":
                await manager.broadcast_to_room(
                    {
                        "type": "message_updated",
                        "data": data,
                        "timestamp": data.get('updated_at')
                    },
                    str(room_id)
                )

            elif event_type == "message_deleted":
                await manager.broadcast_to_room(
                    {
                        "type": "message_deleted",
                        "data": data,
                        "timestamp": data.get('deleted_at')
                    },
                    str(room_id)
                )

            elif event_type == "sync_required":
                # Принудительная синхронизация состояния
                await manager.broadcast_to_room(
                    {
                        "type": "force_sync",
                        "room_id": room_id,
                        "reason": data.get('action', 'state_updated'),
                        "timestamp": manager._get_timestamp()
                    },
                    str(room_id)
                )
                logger.info(f"🔄 WebSocket: принудительная синхронизация для комнаты {room_id}")

            # СИНХРОНИЗАЦИЯ: Обновляем состояние комнаты после важных событий
            if event_type in ["new_message", "message_updated", "message_deleted", "sync_required"]:
                await self._sync_room_state(str(room_id))

        except Exception as e:
            logger.error(f"❌ Ошибка в WebSocketSubscriber: {e}")

    async def _sync_room_state(self, room_id: str):
        """Синхронизация состояния комнаты"""
        try:
            participants = manager.get_room_participants(room_id)

            await manager.broadcast_to_room(
                {
                    "type": "room_state_update",
                    "room_id": room_id,
                    "participants": participants,
                    "participants_count": len(participants),
                    "timestamp": manager._get_timestamp()
                },
                room_id
            )
            logger.debug(f"🔄 Состояние комнаты {room_id} синхронизировано")

        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации состояния комнаты {room_id}: {e}")

    def register(self):
        """Зарегистрировать подписчика для всех комнат"""
        if not self.is_registered:
            # Подписываемся на глобальные события
            chat_observer.subscribe("global", self.handle_chat_event)
            self.is_registered = True
            logger.info("✅ WebSocketSubscriber зарегистрирован для всех комнат")

    def unregister(self):
        """Отписать подписчика"""
        if self.is_registered:
            chat_observer.unsubscribe("global", self.handle_chat_event)
            self.is_registered = False
            logger.info("✅ WebSocketSubscriber отписан")


# Глобальный экземпляр подписчика
websocket_subscriber = WebSocketSubscriber()
