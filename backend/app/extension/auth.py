import hmac

from fastapi import Header, HTTPException, status

from backend.app.core.config import get_settings


def require_extension_api_token(authorization: str | None = Header(default=None)) -> None:
    configured_token = get_settings().chrome_extension_api_token.get_secret_value()
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chrome extension API is not configured",
        )
    scheme, separator, supplied_token = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not hmac.compare_digest(
            configured_token.encode("utf-8"),
            supplied_token.encode("utf-8"),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid Chrome extension bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
