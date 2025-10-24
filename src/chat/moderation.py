import re
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import joinedload

from src.db.models import (
    User, Message, MessageModeration, ChatRoom, ChatParticipant,
    MessageStatus, UserStatus
)
from src.chat.schemas import MessageModerationCreate, MessageModerationResponse
from src.core.config_log import logger

class ContentFilter:
    """Фильтр контента для модерации сообщений."""
    
    def __init__(self):
        # Список запрещенных слов (можно расширить)
        self.banned_words = [
            "спам", "реклама", "мошенничество", "обман",
            "взлом", "хак", "кража", "убийство", "смерть"
        ]
        
        # Регулярные выражения для фильтрации
        self.patterns = [
            r'https?://[^\s]+',  # URL
            r'@\w+',  # Упоминания
            r'#\w+',  # Хештеги
            r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Номера карт
            r'\b\d{3}[\s-]?\d{3}[\s-]?\d{4}\b',  # Телефоны
        ]
        
        # Минимальная длина сообщения
        self.min_length = 1
        # Максимальная длина сообщения
        self.max_length = 2000
    
    def check_content(self, content: str) -> Dict[str, Any]:
        """
        Проверка контента на соответствие правилам.
        
        Returns:
            Dict с результатами проверки:
            - is_valid: bool - валидно ли сообщение
            - violations: List[str] - список нарушений
            - filtered_content: str - отфильтрованное содержимое
        """
        violations = []
        filtered_content = content
        
        # Проверка длины
        if len(content) < self.min_length:
            violations.append("Сообщение слишком короткое")
        
        if len(content) > self.max_length:
            violations.append("Сообщение слишком длинное")
            filtered_content = content[:self.max_length]
        
        # Проверка на запрещенные слова
        content_lower = content.lower()
        for word in self.banned_words:
            if word in content_lower:
                violations.append(f"Запрещенное слово: {word}")
                # Заменяем запрещенные слова на звездочки
                filtered_content = re.sub(
                    re.escape(word), 
                    "*" * len(word), 
                    filtered_content, 
                    flags=re.IGNORECASE
                )
        
        # Проверка на подозрительные паттерны
        for pattern in self.patterns:
            matches = re.findall(pattern, content)
            if matches:
                if pattern.startswith(r'https?://'):
                    violations.append("Обнаружены ссылки")
                elif pattern.startswith(r'@'):
                    violations.append("Обнаружены упоминания")
                elif pattern.startswith(r'#'):
                    violations.append("Обнаружены хештеги")
                elif 'карт' in pattern:
                    violations.append("Обнаружены номера карт")
                elif 'телефон' in pattern:
                    violations.append("Обнаружены номера телефонов")
        
        # Проверка на повторяющиеся символы (спам)
        if self._is_spam(content):
            violations.append("Подозрение на спам")
        
        return {
            "is_valid": len(violations) == 0,
            "violations": violations,
            "filtered_content": filtered_content
        }
    
    def _is_spam(self, content: str) -> bool:
        """Проверка на спам."""
        # Проверка на повторяющиеся символы
        if len(set(content)) < len(content) * 0.3:
            return True
        
        # Проверка на повторяющиеся слова
        words = content.split()
        if len(words) > 3:
            word_counts = {}
            for word in words:
                word_counts[word] = word_counts.get(word, 0) + 1
                if word_counts[word] > len(words) * 0.5:
                    return True
        
        return False


class ModerationService:
    """Сервис модерации сообщений."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.content_filter = ContentFilter()
    
    async def moderate_message(
        self,
        message_id: int,
        moderator_id: int,
        action: str,
        reason: Optional[str] = None
    ) -> MessageModeration:
        """Модерация сообщения."""
        try:
            # Получаем сообщение
            message_query = select(Message).where(Message.message_id == message_id)
            message_result = await self.db.execute(message_query)
            message = message_result.scalar_one_or_none()
            
            if not message:
                raise ValueError("Сообщение не найдено")
            
            # Создаем запись модерации
            moderation = MessageModeration(
                message_id=message_id,
                moderator_id=moderator_id,
                action=action,
                reason=reason
            )
            
            self.db.add(moderation)
            
            # Обновляем статус сообщения
            if action == "approve":
                message.status = MessageStatus.DELIVERED
            elif action == "reject":
                message.status = MessageStatus.MODERATED
            elif action == "delete":
                message.status = MessageStatus.DELETED
                message.is_deleted = True
            
            await self.db.commit()
            await self.db.refresh(moderation)
            
            logger.info(f"Сообщение {message_id} отмодерировано: {action}")
            return moderation
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка модерации сообщения: {e}")
            raise
    
    async def auto_moderate_message(self, message: Message) -> Dict[str, Any]:
        """Автоматическая модерация сообщения."""
        try:
            # Проверяем контент
            filter_result = self.content_filter.check_content(message.content)
            
            if not filter_result["is_valid"]:
                # Автоматически отклоняем сообщение
                moderation = MessageModeration(
                    message_id=message.message_id,
                    moderator_id=1,  # Системный модератор
                    action="reject",
                    reason=f"Автоматическая модерация: {', '.join(filter_result['violations'])}"
                )
                
                self.db.add(moderation)
                
                # Обновляем статус сообщения
                message.status = MessageStatus.MODERATED
                message.content = filter_result["filtered_content"]
                
                await self.db.commit()
                
                logger.info(f"Сообщение {message.message_id} автоматически отмодерировано")
                
                return {
                    "moderated": True,
                    "action": "reject",
                    "reason": filter_result["violations"]
                }
            
            return {
                "moderated": False,
                "action": "approve",
                "reason": []
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка автоматической модерации: {e}")
            raise
    
    async def get_pending_messages(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Message]:
        """Получение сообщений, ожидающих модерации."""
        try:
            query = select(Message).options(
                joinedload(Message.sender),
                joinedload(Message.room)
            ).where(
                and_(
                    Message.status == MessageStatus.SENT,
                    Message.is_deleted == False
                )
            ).order_by(Message.created_at.desc())
            
            query = query.offset(offset).limit(limit)
            
            result = await self.db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Ошибка получения сообщений для модерации: {e}")
            raise
    
    async def get_moderation_history(
        self,
        message_id: Optional[int] = None,
        moderator_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[MessageModerationResponse]:
        """Получение истории модерации."""
        try:
            query = select(MessageModeration).options(
                joinedload(MessageModeration.moderator),
                joinedload(MessageModeration.message)
            )
            
            if message_id:
                query = query.where(MessageModeration.message_id == message_id)
            
            if moderator_id:
                query = query.where(MessageModeration.moderator_id == moderator_id)
            
            query = query.order_by(MessageModeration.moderated_at.desc())
            query = query.offset(offset).limit(limit)
            
            result = await self.db.execute(query)
            moderations = result.scalars().all()
            
            response = []
            for moderation in moderations:
                response.append(MessageModerationResponse(
                    moderation_id=moderation.moderation_id,
                    message_id=moderation.message_id,
                    moderator_id=moderation.moderator_id,
                    moderator_name=moderation.moderator.user_full_name if moderation.moderator else None,
                    action=moderation.action,
                    reason=moderation.reason,
                    moderated_at=moderation.moderated_at
                ))
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка получения истории модерации: {e}")
            raise
    
    async def get_moderation_stats(self) -> Dict[str, Any]:
        """Получение статистики модерации."""
        try:
            # Общее количество сообщений
            total_query = select(func.count(Message.message_id))
            total_result = await self.db.execute(total_query)
            total_messages = total_result.scalar()
            
            # Сообщения по статусам
            status_query = select(
                Message.status,
                func.count(Message.message_id)
            ).group_by(Message.status)
            
            status_result = await self.db.execute(status_query)
            status_stats = dict(status_result.all())
            
            # Количество модераций по действиям
            moderation_query = select(
                MessageModeration.action,
                func.count(MessageModeration.moderation_id)
            ).group_by(MessageModeration.action)
            
            moderation_result = await self.db.execute(moderation_query)
            moderation_stats = dict(moderation_result.all())
            
            return {
                "total_messages": total_messages,
                "status_distribution": status_stats,
                "moderation_actions": moderation_stats
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики модерации: {e}")
            raise
    
    async def bulk_moderate_messages(
        self,
        message_ids: List[int],
        moderator_id: int,
        action: str,
        reason: Optional[str] = None
    ) -> int:
        """Массовая модерация сообщений."""
        try:
            moderated_count = 0
            
            for message_id in message_ids:
                try:
                    await self.moderate_message(message_id, moderator_id, action, reason)
                    moderated_count += 1
                except Exception as e:
                    logger.error(f"Ошибка модерации сообщения {message_id}: {e}")
                    continue
            
            return moderated_count
            
        except Exception as e:
            logger.error(f"Ошибка массовой модерации: {e}")
            raise


class ModerationManager:
    """Менеджер модерации для интеграции с другими сервисами."""
    
    @staticmethod
    async def moderate_new_message(db: AsyncSession, message: Message) -> Dict[str, Any]:
        """Автоматическая модерация нового сообщения."""
        service = ModerationService(db)
        return await service.auto_moderate_message(message)
    
    @staticmethod
    async def moderate_message_manual(
        db: AsyncSession,
        message_id: int,
        moderator_id: int,
        action: str,
        reason: Optional[str] = None
    ) -> MessageModeration:
        """Ручная модерация сообщения."""
        service = ModerationService(db)
        return await service.moderate_message(message_id, moderator_id, action, reason)
    
    @staticmethod
    async def get_moderation_queue(db: AsyncSession, limit: int = 50) -> List[Message]:
        """Получение очереди модерации."""
        service = ModerationService(db)
        return await service.get_pending_messages(limit=limit)
    
    @staticmethod
    async def get_moderation_stats(db: AsyncSession) -> Dict[str, Any]:
        """Получение статистики модерации."""
        service = ModerationService(db)
        return await service.get_moderation_stats()
