"""services.user_service — facade re-exporting from api.routes.user_service."""

from api.routes.user_service import (  # noqa: F401
    create_user,
    get_user,
    authenticate_user,
)

__all__ = ["create_user", "get_user", "authenticate_user"]
