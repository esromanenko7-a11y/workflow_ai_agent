from aiogram.filters import BaseFilter
from aiogram.types import Message

from bot.config import get_bot_settings


class IsAdmin(BaseFilter):
    async def __call__(
        self,
        message: Message,
    ) -> bool:
        if message.from_user is None:
            return False

        settings = get_bot_settings()

        return message.from_user.id in settings.bot_admin_ids
