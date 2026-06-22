"""ui.sidebar — facade stub for Streamlit sidebar."""



def render_sidebar(state=None) -> None:
    """Render the Streamlit sidebar (stub)."""
    try:
        import streamlit as st
        st.sidebar.title("Smart Land Copilot")
        st.sidebar.markdown("Navigation placeholder")
    except ImportError:
        pass


__all__ = ["render_sidebar"]
