from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
import httpx


class NotifierSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_url: str = Field(
        default="http://127.0.0.1:9000",
        validation_alias="BOT_URL",
    )
    internal_token: SecretStr = Field(
        validation_alias="INTERNAL_TOKEN",
    )


async def notify_user(
    chat_id_tg: int,
    text: str,
    settings: NotifierSettings | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    current_settings = settings or NotifierSettings()

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        timeout=5.0,
        trust_env=False,
    )

    try:
        response = await http_client.post(
            f"{current_settings.bot_url.rstrip('/')}/notify",
            json={
                "chat_id": chat_id_tg,
                "text": text,
            },
            headers={
                "X-Internal-Token": (
                    current_settings.internal_token.get_secret_value()
                ),
            },
        )
        response.raise_for_status()
    finally:
        if owns_client:
            await http_client.aclose()
