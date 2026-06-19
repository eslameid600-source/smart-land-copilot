"""
============================================================
Smart Land Management Copilot — Chat View
============================================================
Renders the chat interface with message history, streaming
GLM responses, and suggestion chips.

Design Pattern: View (MVP), Observer (reacts to state changes)
SOLID: SRP — chat rendering and interaction only
============================================================
"""

from __future__ import annotations

import streamlit as st
from typing import Optional

from services.state_manager import get_state, ChatMessage
from services.rag_service import get_rag_service
from services.glm_service import get_glm_service


# ----------------------------------------------------------
# Suggestion Chips
# ----------------------------------------------------------

SUGGESTION_CHIPS: list[str] = [
    "Show me industrial land in Sharqia",
    "Agricultural land under 2000 EGP/sqm",
    "Logistics near Suez Canal",
    "Best residential investment in Cairo",
    "All auction opportunities",
    "Land with gas and fiber-optic",
]


def render_chat_view() -> None:
    """
    Render the complete chat view (left panel, 40% width).

    This is the main entry point for the chat UI.
    """
    state = get_state()

    st.subheader("AI Land Advisor")
    st.caption("Ask about any land in Egypt — the AI searches the database and provides feasibility analysis.")

    # --- Render message history ---
    _render_history(state)

    # --- Suggestion chips (only when chat is empty) ---
    if state.chat.is_empty and not state.chat.is_processing:
        _render_suggestion_chips()

    # --- Auto-query from map click ---
    if state.chat.auto_query_from_map:
        auto_query = state.chat.auto_query_from_map
        state.chat.auto_query_from_map = None
        _process_query(auto_query, state)

    # --- Chat input ---
    user_input = st.chat_input(
        "Ask about Egyptian land investments...",
        key="chat_input_main",
        disabled=state.chat.is_processing,
    )

    if user_input:
        _process_query(user_input, state)


def _render_history(state) -> None:
    """Render existing chat messages."""
    for msg in state.chat.messages:
        with st.chat_message(msg.role):
            st.write_stream(_text_stream(msg.content))


def _render_suggestion_chips() -> None:
    """Render clickable suggestion chips."""
    cols = st.columns(2)
    for i, chip in enumerate(SUGGESTION_CHIPS):
        with cols[i % 2]:
            if st.button(chip, key=f"chip_{i}", use_container_width=True):
                state.chat.auto_query_from_map = chip
                st.rerun()


def _process_query(user_input: str, state) -> None:
    """
    Process a user query through the full RAG pipeline.

    Pipeline: Input → RAG Search → Context Format → GLM Stream → Display
    """
    # Add user message to history
    state.chat.add_user_message(user_input)
    state.chat.is_processing = True

    # Display user message
    with st.chat_message("user"):
        st.write(user_input)

    # RAG retrieval
    rag_service = get_rag_service()
    results = rag_service.search(user_input, top_k=5)
    context_text = rag_service.build_context(results)

    # Store in search state
    state.search.set_results(results, context=context_text)

    # Stream assistant response
    with st.chat_message("assistant"):
        response_stream = st.write_stream(
            get_glm_service().stream_chat(user_input, context_text)
        )

    # Store assistant message
    state.chat.add_assistant_message(response_stream)
    state.chat.is_processing = False


def _text_stream(text: str):
    """Generator that yields text for st.write_stream (non-streaming display)."""
    yield text