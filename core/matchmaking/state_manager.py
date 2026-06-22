"""
============================================================
Smart Land Management Copilot — Session State Manager
============================================================
Centralized session state management for Streamlit.

Instead of directly manipulating st.session_state throughout the
codebase, this module provides typed accessors with validation
and encapsulation.

Design Pattern: State Pattern, Facade
SOLID:
  - SRP: State management only
  - DIP: UI depends on state manager, not raw session_state
============================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

logger = logging.getLogger(__name__)


# ----------------------------------------------------------
# State Data Classes
# ----------------------------------------------------------

@dataclass
class ChatMessage:
    """A single chat message with role and content."""
    role: str  # "user" or "assistant"
    content: str

    def to_tuple(self) -> Tuple[str, str]:
        return (self.role, self.content)

    @classmethod
    def from_tuple(cls, data: Tuple[str, str]) -> "ChatMessage":
        return cls(role=data[0], content=data[1])


@dataclass
class ChatState:
    """Manages chat history and input state."""
    messages: List[ChatMessage] = field(default_factory=list)
    last_query: str = ""
    is_processing: bool = False
    auto_query_from_map: Optional[str] = None

    def add_user_message(self, content: str) -> None:
        self.messages.append(ChatMessage(role="user", content=content))
        self.last_query = content
        # Trim history if too long
        max_history = 50
        if len(self.messages) > max_history * 2:  # user + assistant pairs
            self.messages = self.messages[-(max_history * 2):]

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(ChatMessage(role="assistant", content=content))

    def clear(self) -> None:
        self.messages.clear()
        self.last_query = ""
        self.auto_query_from_map = None

    @property
    def is_empty(self) -> bool:
        return len(self.messages) == 0

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass
class SearchState:
    """Manages search results and query state."""
    results: List[Tuple[Dict[str, Any], int]] = field(default_factory=list)
    last_intent: Optional[Dict[str, Any]] = None
    context_text: str = ""

    def set_results(
        self,
        results: List[Tuple[Dict[str, Any], int]],
        intent: Optional[Dict[str, Any]] = None,
        context: str = "",
    ) -> None:
        self.results = results
        self.last_intent = intent
        self.context_text = context

    def clear(self) -> None:
        self.results = []
        self.last_intent = None
        self.context_text = ""


@dataclass
class MatchmakingState:
    """Manages matchmaking results and criteria."""
    criteria: Optional[Dict[str, Any]] = None
    report_data: Optional[List[Dict[str, Any]]] = None
    criteria_summary: str = ""
    context_text: str = ""
    is_running: bool = False
    llm_analysis_done: bool = False

    def set_criteria(self, criteria: Dict[str, Any]) -> None:
        self.criteria = criteria

    def set_results(
        self,
        report_data: List[Dict[str, Any]],
        criteria_summary: str,
        context_text: str,
    ) -> None:
        self.report_data = report_data
        self.criteria_summary = criteria_summary
        self.context_text = context_text
        self.is_running = False

    def clear(self) -> None:
        self.criteria = None
        self.report_data = None
        self.criteria_summary = ""
        self.context_text = ""
        self.is_running = False
        self.llm_analysis_done = False


@dataclass
class MapState:
    """Manages map interaction state."""
    selected_usage_filter: str = "All"
    highlighted_land_id: Optional[str] = None
    last_clicked_coords: Optional[Tuple[float, float]] = None
    needs_rebuild: bool = True

    def set_filter(self, usage: str) -> None:
        if self.selected_usage_filter != usage:
            self.selected_usage_filter = usage
            self.needs_rebuild = True

    def set_highlight(self, land_id: Optional[str]) -> None:
        if self.highlighted_land_id != land_id:
            self.highlighted_land_id = land_id
            self.needs_rebuild = True


# ----------------------------------------------------------
# State Manager (Facade)
# ----------------------------------------------------------

_STATE_KEY = "__land_copilot_state__"


class StateManager:
    """
    Centralized Streamlit session state manager.

    Provides typed, validated access to all application state
    through dedicated state objects instead of raw dict access.
    """

    def __init__(self) -> None:
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Initialize state if not already done."""
        if _STATE_KEY not in st.session_state:
            st.session_state[_STATE_KEY] = {
                "chat": ChatState(),
                "search": SearchState(),
                "matchmaking": MatchmakingState(),
                "map": MapState(),
            }
            logger.debug("Session state initialized")

    # ----------------------------------------------------------
    # Typed Accessors
    # ----------------------------------------------------------

    @property
    def chat(self) -> ChatState:
        return st.session_state[_STATE_KEY]["chat"]

    @property
    def search(self) -> SearchState:
        return st.session_state[_STATE_KEY]["search"]

    @property
    def matchmaking(self) -> MatchmakingState:
        return st.session_state[_STATE_KEY]["matchmaking"]

    @property
    def map(self) -> MapState:
        return st.session_state[_STATE_KEY]["map"]

    # ----------------------------------------------------------
    # Convenience Methods
    # ----------------------------------------------------------

    def reset_all(self) -> None:
        """Reset all state to defaults."""
        st.session_state[_STATE_KEY] = {
            "chat": ChatState(),
            "search": SearchState(),
            "matchmaking": MatchmakingState(),
            "map": MapState(),
        }
        logger.info("All session state reset")

    def invalidate_map_cache(self) -> None:
        """Force map rebuild on next render."""
        self.map.needs_rebuild = True


# ----------------------------------------------------------
# Module-level singleton
# ----------------------------------------------------------

_state_manager: Optional[StateManager] = None


def get_state() -> StateManager:
    """Get or create the global state manager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


def reset_state() -> None:
    """Reset the state manager and all state (useful for testing)."""
    global _state_manager
    _state_manager = None