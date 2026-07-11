from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(
        validation_alias="BOT_TOKEN",
    )
    backend_url: str = Field(
        default="http://127.0.0.1:8001",
        validation_alias="BACKEND_URL",
    )
    bot_admin_ids: list[int] = Field(
        default_factory=list,
        validation_alias="BOT_ADMIN_IDS",
    )
    bot_proxy: str | None = Field(
        default=None,
        validation_alias="BOT_PROXY",
    )
    bot_verify_ssl: bool = Field(
        default=True,
        validation_alias="BOT_VERIFY_SSL",
    )


@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()
