"""ui.map_view — facade stub for the map UI panel."""


def render_map_view(state=None) -> None:
    """Render the map view panel (stub)."""
    try:
        import streamlit as st
        from services.map_service import get_land_map_html
        st.subheader("Land Map")
        try:
            st.components.v1.html(get_land_map_html(), height=600)
        except Exception:
            st.info("Map unavailable in this environment.")
    except ImportError:
        pass


__all__ = ["render_map_view"]
