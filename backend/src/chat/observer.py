from typing import List, Callable, Dict, Any
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

        self._subscribers[room_id].append(callback)
        logger.debug(f"Подписка на комнату {room_id}. Всего подписчиков: {len(self._subscribers[room_id])}")

    def subscribe_global(self, callback: Callable):
        """Подписаться на события всех комнат"""
        self._global_subscribers.append(callback)
        logger.debug(f"Глобальная подписка. Всего глобальных подписчиков: {len(self._global_subscribers)}")

    def unsubscribe(self, room_id: int, callback: Callable):
        """Отписаться от событий комнаты"""
        if room_id in self._subscribers:
            if callback in self._subscribers[room_id]:
                self._subscribers[room_id].remove(callback)
                logger.debug(f"Отписка от комнаты {room_id}. Осталось: {len(self._subscribers[room_id])}")

    async def notify(self, room_id: int, event_type: str, data: Dict[str, Any]):
        """Уведомить всех подписчиков о событии"""
        logger.info(f"🔔 Observer: уведомление {event_type} для комнаты {room_id}")

        tasks = []

        # Уведомляем глобальных подписчиков
        for callback in self._global_subscribers:
            try:
                task = asyncio.create_task(callback(event_type, data))
                tasks.append(task)
            except Exception as e:
                logger.error(f"Ошибка в глобальном callback для комнаты {room_id}: {e}")

        # Уведомляем подписчиков конкретной комнаты
        if room_id in self._subscribers:
            for callback in self._subscribers[room_id]:
                try:
                    task = asyncio.create_task(callback(event_type, data))
                    tasks.append(task)
                except Exception as e:
                    logger.error(f"Ошибка в callback для комнаты {room_id}: {e}")

        # Ждем завершения всех задач
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Ошибка в обработчике события: {result}")


# Глобальный экземпляр Observer
chat_observer = ChatObserver()
