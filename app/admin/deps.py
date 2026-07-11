import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


def require_admin(
    x_admin_token: Annotated[
        str | None,
        Header(alias="X-Admin-Token"),
    ] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Token",
        )

    expected_token = settings.admin_token.get_secret_value()

    if not expected_token or not secrets.compare_digest(
        x_admin_token,
        expected_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token",
        )
