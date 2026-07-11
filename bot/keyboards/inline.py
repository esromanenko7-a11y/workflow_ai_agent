from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


TOPICS: dict[str, str] = {
    "package_errors": "Ошибки пакета",
    "warnings": "Предупреждения",
    "transfer_status": "Статус передачи",
    "business_rules": "Бизнес-правила",
    "data_format": "Формат данных",
}


def get_topic_title(slug: str) -> str:
    return TOPICS.get(slug, slug)


def topics_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for slug, title in TOPICS.items():
        builder.button(
            text=title,
            callback_data=f"topic:{slug}",
        )

    builder.button(
        text="Отмена",
        callback_data="topic:cancel",
    )

    builder.adjust(1)

    return builder.as_markup()
