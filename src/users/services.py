from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import User, UserStatus
from src.core.config_log import logger


class UserService:
    """Сервис для управления пользователями"""

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
        """Получить пользователя по ID"""
        result = await db.execute(
            select(User).where(User.user_id == user_id, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("Пользователь не найден")
        return user

    @staticmethod
    async def validate_user_management(
            target_user: User,
            current_user: User,
            allow_self_operation: bool = False,
            allow_admin_management: bool = False
    ):
        """Валидация прав для управления пользователями"""
        if target_user.user_id == 1:
            raise ValueError("С пользователем с id=1 нельзя выполнять это действие")

        if not allow_self_operation and target_user.user_id == current_user.user_id:
            raise ValueError("Нельзя выполнять это действие над собой")

        if not allow_admin_management and target_user.role_id == 1:
            raise ValueError("Недостаточно прав для управления администраторами")

    @staticmethod
    async def change_user_role(
            db: AsyncSession,
            target_user_id: int,
            new_role_id: int,
            current_user_id: int
    ):
        """Изменить роль пользователя"""
        target_user = await UserService.get_user_by_id(db, target_user_id)
        current_user = await UserService.get_user_by_id(db, current_user_id)

        await UserService.validate_user_management(
            target_user, current_user,
            allow_self_operation=False,
            allow_admin_management=True  # Только админы могут менять роли
        )

        if new_role_id not in (1, 2, 3):
            raise ValueError("Неверная роль")

        await db.execute(
            update(User)
            .where(User.user_id == target_user_id)
            .values(role_id=new_role_id)
        )
        await db.commit()

        logger.info(f"Пользователь {current_user_id} изменил роль пользователя {target_user_id} на {new_role_id}")

    @staticmethod
    async def ban_user(
            db: AsyncSession,
            target_user_id: int,
            current_user_id: int,
            reason: str = None
    ):
        """Заблокировать пользователя"""
        target_user = await UserService.get_user_by_id(db, target_user_id)
        current_user = await UserService.get_user_by_id(db, current_user_id)

        await UserService.validate_user_management(
            target_user, current_user,
            allow_self_operation=False,
            allow_admin_management=False  # Модераторы не могут банить админов
        )

        updates = {"status": UserStatus.BANNED}
        if hasattr(target_user, "ban_reason"):
            updates["ban_reason"] = reason
        if hasattr(target_user, "banned_at"):
            updates["banned_at"] = datetime.now(timezone.utc)

        await db.execute(
            update(User)
            .where(User.user_id == target_user_id)
            .values(**updates)
        )
        await db.commit()

        logger.info(f"Пользователь {current_user_id} заблокировал пользователя {target_user_id}")

    @staticmethod
    async def unban_user(
            db: AsyncSession,
            target_user_id: int,
            current_user_id: int
    ):
        """Разблокировать пользователя"""
        target_user = await UserService.get_user_by_id(db, target_user_id)
        current_user = await UserService.get_user_by_id(db, current_user_id)

        await UserService.validate_user_management(
            target_user, current_user,
            allow_self_operation=False,
            allow_admin_management=False
        )

        if target_user.status != UserStatus.BANNED:
            raise ValueError("Пользователь не заблокирован")

        await db.execute(
            update(User)
            .where(User.user_id == target_user_id)
            .values(status=UserStatus.ACTIVE)
        )
        await db.commit()

        logger.info(f"Пользователь {current_user_id} разблокировал пользователя {target_user_id}")

    @staticmethod
    async def delete_user(
            db: AsyncSession,
            target_user_id: int,
            current_user_id: int
    ):
        """Удалить пользователя"""
        target_user = await UserService.get_user_by_id(db, target_user_id)
        current_user = await UserService.get_user_by_id(db, current_user_id)

        await UserService.validate_user_management(
            target_user, current_user,
            allow_self_operation=False,
            allow_admin_management=True  # Только админы могут удалять админов
        )

        await db.execute(
            update(User)
            .where(User.user_id == target_user_id)
            .values(is_deleted=True)
        )
        await db.commit()

        logger.info(f"Пользователь {current_user_id} удалил пользователя {target_user_id}")

    @staticmethod
    async def restore_user(
            db: AsyncSession,
            target_user_id: int,
            current_user_id: int
    ):
        """Восстановить пользователя"""
        result = await db.execute(
            select(User).where(User.user_id == target_user_id, User.is_deleted == True)
        )
        target_user = result.scalar_one_or_none()
        if not target_user:
            raise ValueError("Пользователь не найден или не удалён")

        current_user = await UserService.get_user_by_id(db, current_user_id)

        await UserService.validate_user_management(
            target_user, current_user,
            allow_self_operation=False,
            allow_admin_management=True
        )

        await db.execute(
            update(User)
            .where(User.user_id == target_user_id)
            .values(is_deleted=False)
        )
        await db.commit()

        logger.info(f"Пользователь {current_user_id} восстановил пользователя {target_user_id}")