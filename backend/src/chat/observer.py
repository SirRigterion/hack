from typing import List, Callable, Dict, Any, Optional
import asyncio
from src.core.config_log import logger


class ChatObserver:
    """
    Observer для управления подписками на события чата
    """

    def __init__(self):
        # room_id -> list of callback functions
        self._subscribers: Dict[int, List[Callable]] = {}
        # Глобальные подписчики (для всех комнат)
        self._global_subscribers: List[Callable] = []

    def subscribe(self, room_id: int, callback: Callable):
        """Подписаться на события комнаты"""
        if room_id not in self._subscribers:
            self._subscribers[room_id] = []

        if callback not in self._subscribers[room_id]:
            self._subscribers[room_id].append(callback)
            logger.debug(f"✅ Подписка на комнату {room_id}. Всего подписчиков: {len(self._subscribers[room_id])}")
        else:
            logger.debug(f"⚠️ Callback уже подписан на комнату {room_id}")

    def subscribe_global(self, callback: Callable):
        """Подписаться на события всех комнат"""
        if callback not in self._global_subscribers:
            self._global_subscribers.append(callback)
            logger.debug(f"✅ Глобальная подписка. Всего глобальных подписчиков: {len(self._global_subscribers)}")
        else:
            logger.debug("⚠️ Callback уже подписан глобально")

    def unsubscribe(self, room_id: int, callback: Callable):
        """Отписаться от событий комнаты"""
        if room_id in self._subscribers:
            if callback in self._subscribers[room_id]:
                self._subscribers[room_id].remove(callback)
                logger.debug(f"✅ Отписка от комнаты {room_id}. Осталось: {len(self._subscribers[room_id])}")

                # Удаляем пустой список подписчиков
                if not self._subscribers[room_id]:
                    del self._subscribers[room_id]
            else:
                logger.debug(f"⚠️ Callback не найден в подписчиках комнаты {room_id}")

    def unsubscribe_global(self, callback: Callable):
        """Отписаться от глобальных событий"""
        if callback in self._global_subscribers:
            self._global_subscribers.remove(callback)
            logger.debug(f"✅ Глобальная отписка. Осталось: {len(self._global_subscribers)}")
        else:
            logger.debug("⚠️ Callback не найден в глобальных подписчиках")

    async def notify(self, room_id: int, event_type: str, data: Dict[str, Any]):
        """Уведомить всех подписчиков о событии"""
        total_subscribers = len(self._global_subscribers) + len(self._subscribers.get(room_id, []))

        logger.info(f"🔔 Observer: {event_type} для комнаты {room_id}, подписчиков: {total_subscribers}")

        tasks = []
        errors = []

        # Уведомляем глобальных подписчиков
        for callback in self._global_subscribers:
            try:
                task = asyncio.create_task(callback(event_type, data))
                tasks.append(task)
            except Exception as e:
                logger.error(f"❌ Ошибка в глобальном callback для комнаты {room_id}: {e}")
                errors.append(e)

        # Уведомляем подписчиков конкретной комнаты
        if room_id in self._subscribers:
            for callback in self._subscribers[room_id]:
                try:
                    task = asyncio.create_task(callback(event_type, data))
                    tasks.append(task)
                except Exception as e:
                    logger.error(f"❌ Ошибка в callback для комнаты {room_id}: {e}")
                    errors.append(e)

        # Ждем завершения всех задач
        if tasks:
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Логируем ошибки из результатов
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ Ошибка выполнения в обработчике {i}: {result}")
                        errors.append(result)
            except Exception as e:
                logger.error(f"❌ Ошибка при выполнении задач уведомления: {e}")
                errors.append(e)

        # Логируем итоги уведомления
        if errors:
            logger.warning(f"⚠️ Уведомление для комнаты {room_id} завершено с {len(errors)} ошибками")
        else:
            logger.debug(f"✅ Уведомление для комнаты {room_id} успешно доставлено {len(tasks)} подписчикам")

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику подписчиков"""
        room_subscribers = {room_id: len(callbacks) for room_id, callbacks in self._subscribers.items()}

        return {
            "total_rooms": len(self._subscribers),
            "total_global_subscribers": len(self._global_subscribers),
            "room_subscribers": room_subscribers,
            "total_subscribers": len(self._global_subscribers) + sum(room_subscribers.values())
        }

    def clear_room_subscribers(self, room_id: int):
        """Очистить всех подписчиков комнаты"""
        if room_id in self._subscribers:
            count = len(self._subscribers[room_id])
            del self._subscribers[room_id]
            logger.info(f"🧹 Очищены все подписчики комнаты {room_id} ({count} подписчиков)")

    def clear_all(self):
        """Очистить всех подписчиков"""
        total_rooms = len(self._subscribers)
        total_global = len(self._global_subscribers)
        total_subscribers = sum(len(callbacks) for callbacks in self._subscribers.values()) + total_global

        self._subscribers.clear()
        self._global_subscribers.clear()

        logger.info(
            f"🧹 Очищены все подписчики: {total_rooms} комнат, {total_global} глобальных, {total_subscribers} всего")


# Глобальный экземпляр Observer
chat_observer = ChatObserver()
