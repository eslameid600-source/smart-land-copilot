"""purchase_module.auth — facade re-exporting JWT helpers from api.routes.auth.

`api.routes.auth` exposes `verify_token` (not `decode_access_token`).
We re-export `verify_token` under the legacy `decode_access_token` alias
for backwards compatibility.
"""

from api.routes.auth import (  # noqa: F401
    configure_auth,
    create_access_token,
    verify_token,
    get_current_user,
    require_role,
)

# Legacy alias — older code imports `decode_access_token`
decode_access_token = verify_token

__all__ = [
    "configure_auth",
    "create_access_token",
    "decode_access_token",
    "verify_token",
    "get_current_user",
    "require_role",
]
