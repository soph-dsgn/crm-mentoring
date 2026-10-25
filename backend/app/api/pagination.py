from __future__ import annotations

import base64
import binascii

from fastapi import status

from app.api.errors import ApiError


def encode_cursor(resource_id: str) -> str:
    return base64.urlsafe_b64encode(resource_id.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if cursor is None:
        return None
    try:
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        value = decoded.decode()
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_cursor",
            "Pagination cursor is invalid",
        ) from error
    if not value:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_cursor",
            "Pagination cursor is invalid",
        )
    return value
