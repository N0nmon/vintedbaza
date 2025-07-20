# Файл: middlewares/access_control.py
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message
from sqlalchemy import select
from db.database import async_session
from db.models import User

class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем, есть ли пользователь в нашей БД
        async with async_session() as session:
            result = await session.execute(select(User).where(User.user_id == event.from_user.id))
            user = result.scalar_one_or_none()

        if user:
            # Если пользователь есть, прокидываем его в хендлер для удобства
            data['user'] = user
            return await handler(event, data)

        # Если пользователя нет, бот ничего не будет делать
        # Можно добавить ответ, например:
        # await event.answer("Доступ запрещен.")