"""ui.chat_view — facade stub for the chat UI panel."""


def render_chat_view(state=None) -> None:
    """Render the chat view panel (stub)."""
    try:
        import streamlit as st
        st.subheader("Chat")
        st.text_input("Ask a question...", key="chat_input")
    except ImportError:
        pass


__all__ = ["render_chat_view"]
