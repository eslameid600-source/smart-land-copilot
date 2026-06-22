"""services.state_manager — facade stub for Streamlit session state."""

from typing import Any, Dict

_state: Dict[str, Any] = {}


def get_state() -> Dict[str, Any]:
    """Return the global session state (in-memory stub)."""
    return _state


def set_state(key: str, value: Any) -> None:
    _state[key] = value


def get(key: str, default: Any = None) -> Any:
    return _state.get(key, default)


__all__ = ["get_state", "set_state", "get"]
