"""
JWT + password authentication for the purchase module.
Integrates with existing user system via a user-lookup callback.
"""

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

SECRET_KEY = "smart-land-copilot-jwt-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Callback to resolve user_id -> user record (set at startup)
_user_lookup: Optional[Callable] = None


def configure_auth(lookup_fn: Callable) -> None:
    """
    Set the user-lookup callback.
    Signature: async fn(user_id: str) -> dict | None
    The dict must contain at least: {"user_id": str, "role": str}
    """
    global _user_lookup
    _user_lookup = lookup_fn


# ──────────────────────────────────────────────
# Token creation & verification
# ──────────────────────────────────────────────

def create_access_token(user_id: str, role: str = "Buyer/Investor") -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token. Raises on invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ──────────────────────────────────────────────
# FastAPI dependency
# ──────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency: extract and validate the current user
    from the Authorization: Bearer <token> header.
    Returns {"sub": user_id, "role": str, ...}
    """
    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )
    return payload


def require_role(*roles: str):
    """
    Dependency factory: enforce that the current user has one of
    the allowed roles.  Usage:
        @router.get("/...", dependencies=[Depends(require_role("Buyer/Investor"))])
    """
    async def _check(payload: dict = Depends(get_current_user)) -> dict:
        user_role = payload.get("role", "")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' not allowed. Required: {roles}",
            )
        return payload
    return _check