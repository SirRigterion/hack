from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import joinedload

from src.db.models import User, Notification, Message, ChatRoom, ChatParticipant
from src.chat.schemas import NotificationResponse, NotificationTypeEnum
from src.chat.websocket_manager import manager
from src.core.config_log import logger


class NotificationService:
    """Сервис для работы с уведомлениями."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_notification(
        self,
        user_id: int,
        notification_type: NotificationTypeEnum,
        title: str,
        content: str,
        message_id: Optional[int] = None
    ) -> Notification:
        """Создание уведомления."""
        try:
            notification = Notification(
                user_id=user_id,
                message_id=message_id,
                notification_type=notification_type.value,
                title=title,
                content=content
            )
            
            self.db.add(notification)
            await self.db.commit()
            await self.db.refresh(notification)
            
            # Отправляем через WebSocket
            await self.send_notification_websocket(notification)
            
            logger.info(f"Создано уведомление {notification.notification_id} для пользователя {user_id}")
            return notification
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка создания уведомления: {e}")
            raise
    
    async def get_user_notifications(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False
    ) -> List[NotificationResponse]:
        """Получение уведомлений пользователя."""
        try:
            query = select(Notification).options(
                joinedload(Notification.message)
            ).where(Notification.user_id == user_id)
            
            if unread_only:
                query = query.where(Notification.is_read == False)
            
            query = query.order_by(Notification.created_at.desc())
            query = query.offset(offset).limit(limit)
            
            result = await self.db.execute(query)
            notifications = result.scalars().all()
            
            response = []
            for notification in notifications:
                response.append(NotificationResponse(
                    notification_id=notification.notification_id,
                    user_id=notification.user_id,
                    message_id=notification.message_id,
                    notification_type=notification.notification_type,
                    title=notification.title,
                    content=notification.content,
                    is_read=notification.is_read,
                    created_at=notification.created_at
                ))
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка получения уведомлений: {e}")
            raise
    
    async def mark_notification_as_read(self, notification_id: int, user_id: int) -> bool:
        """Отметка уведомления как прочитанного."""
        try:
            query = update(Notification).where(
                and_(
                    Notification.notification_id == notification_id,
                    Notification.user_id == user_id
                )
            ).values(is_read=True)
            
            result = await self.db.execute(query)
            await self.db.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка отметки уведомления как прочитанного: {e}")
            raise
    
    async def mark_all_notifications_as_read(self, user_id: int) -> int:
        """Отметка всех уведомлений пользователя как прочитанных."""
        try:
            query = update(Notification).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False
                )
            ).values(is_read=True)
            
            result = await self.db.execute(query)
            await self.db.commit()
            
            return result.rowcount
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка отметки всех уведомлений как прочитанных: {e}")
            raise
    
    async def delete_notification(self, notification_id: int, user_id: int) -> bool:
        """Удаление уведомления."""
        try:
            query = delete(Notification).where(
                and_(
                    Notification.notification_id == notification_id,
                    Notification.user_id == user_id
                )
            )
            
            result = await self.db.execute(query)
            await self.db.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка удаления уведомления: {e}")
            raise
    
    async def get_unread_count(self, user_id: int) -> int:
        """Получение количества непрочитанных уведомлений."""
        try:
            query = select(func.count(Notification.notification_id)).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False
                )
            )
            
            result = await self.db.execute(query)
            return result.scalar() or 0
            
        except Exception as e:
            logger.error(f"Ошибка получения количества непрочитанных уведомлений: {e}")
            raise
    
    async def send_notification_websocket(self, notification: Notification):
        """Отправка уведомления через WebSocket."""
        try:
            notification_data = NotificationResponse(
                notification_id=notification.notification_id,
                user_id=notification.user_id,
                message_id=notification.message_id,
                notification_type=notification.notification_type,
                title=notification.title,
                content=notification.content,
                is_read=notification.is_read,
                created_at=notification.created_at
            ).dict()
            
            await manager.broadcast_notification(notification_data, notification.user_id)
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через WebSocket: {e}")
    
    async def create_message_notifications(
        self,
        message: Message,
        sender_id: int,
        room_id: int
    ):
        """Создание уведомлений о новом сообщении."""
        try:
            # Получаем участников комнаты (кроме отправителя)
            participants_query = select(ChatParticipant).where(
                and_(
                    ChatParticipant.room_id == room_id,
                    ChatParticipant.user_id != sender_id
                )
            )
            participants_result = await self.db.execute(participants_query)
            participants = participants_result.scalars().all()
            
            # Создаем уведомления
            for participant in participants:
                await self.create_notification(
                    user_id=participant.user_id,
                    notification_type=NotificationTypeEnum.NEW_MESSAGE,
                    title="Новое сообщение",
                    content=f"Новое сообщение в чате",
                    message_id=message.message_id
                )
            
        except Exception as e:
            logger.error(f"Ошибка создания уведомлений о сообщении: {e}")
    
    async def create_mention_notifications(
        self,
        message: Message,
        mentioned_user_ids: List[int]
    ):
        """Создание уведомлений об упоминаниях."""
        try:
            for user_id in mentioned_user_ids:
                await self.create_notification(
                    user_id=user_id,
                    notification_type=NotificationTypeEnum.MENTION,
                    title="Вас упомянули",
                    content=f"Вас упомянули в сообщении",
                    message_id=message.message_id
                )
            
        except Exception as e:
            logger.error(f"Ошибка создания уведомлений об упоминаниях: {e}")
    
    async def create_system_notification(
        self,
        user_id: int,
        title: str,
        content: str
    ):
        """Создание системного уведомления."""
        try:
            await self.create_notification(
                user_id=user_id,
                notification_type=NotificationTypeEnum.SYSTEM,
                title=title,
                content=content
            )
            
        except Exception as e:
            logger.error(f"Ошибка создания системного уведомления: {e}")
    
    async def cleanup_old_notifications(self, days: int = 30):
        """Очистка старых уведомлений."""
        try:
            from datetime import datetime, timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            query = delete(Notification).where(
                and_(
                    Notification.created_at < cutoff_date,
                    Notification.is_read == True
                )
            )
            
            result = await self.db.execute(query)
            await self.db.commit()
            
            logger.info(f"Удалено {result.rowcount} старых уведомлений")
            return result.rowcount
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка очистки старых уведомлений: {e}")
            raise


class NotificationManager:
    """Менеджер уведомлений для интеграции с другими сервисами."""
    
    @staticmethod
    async def notify_new_message(db: AsyncSession, message: Message, sender_id: int):
        """Уведомление о новом сообщении."""
        service = NotificationService(db)
        await service.create_message_notifications(message, sender_id, message.room_id)
    
    @staticmethod
    async def notify_mention(db: AsyncSession, message: Message, mentioned_user_ids: List[int]):
        """Уведомление об упоминании."""
        service = NotificationService(db)
        await service.create_mention_notifications(message, mentioned_user_ids)
    
    @staticmethod
    async def notify_system(db: AsyncSession, user_id: int, title: str, content: str):
        """Системное уведомление."""
        service = NotificationService(db)
        await service.create_system_notification(user_id, title, content)
    
    @staticmethod
    async def cleanup_notifications(db: AsyncSession, days: int = 30):
        """Очистка старых уведомлений."""
        service = NotificationService(db)
        return await service.cleanup_old_notifications(days)
