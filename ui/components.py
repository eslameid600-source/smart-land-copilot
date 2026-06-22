"""ui.components — facade stub for shared UI components."""



def render_land_card(land_dict) -> None:
    """Render a single land card (stub)."""
    try:
        import streamlit as st
        st.markdown(f"### {land_dict.get('land_name', land_dict.get('land_id', ''))}")
        st.caption(land_dict.get("governorate", ""))
    except ImportError:
        pass


def render_metric_card(label: str, value: str, color: str = "#27ae60", icon: str = "") -> None:
    """Render a metric card (stub) — colored box with label + value."""
    try:
        import streamlit as st
        st.markdown(
            f"""
            <div style="background:{color}22;border-left:5px solid {color};
                        padding:12px;border-radius:6px;margin:6px 0;">
                <div style="font-size:12px;color:#555;">{label}</div>
                <div style="font-size:22px;font-weight:600;color:{color};">{icon} {value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except ImportError:
        pass


def render_land_table(lands) -> None:
    """Render a table of lands (stub)."""
    try:
        import streamlit as st
        if not lands:
            st.info("No lands to display.")
            return
        st.dataframe(lands, use_container_width=True)
    except ImportError:
        pass


def render_chat_bubble(role: str, message: str) -> None:
    """Render a chat bubble (stub)."""
    try:
        import streamlit as st
        if role == "user":
            st.markdown(f"**You:** {message}")
        else:
            st.markdown(f"**Assistant:** {message}")
    except ImportError:
        pass


def render_section_header(title: str, icon: str = "") -> None:
    """Render a section header (stub) — colored divider with title."""
    try:
        import streamlit as st
        st.markdown(
            f"""
            <div style="border-bottom:2px solid #2c3e50;
                        padding:8px 0;margin:12px 0;">
                <span style="font-size:18px;font-weight:600;color:#2c3e50;">
                    {icon} {title}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except ImportError:
        pass


def render_kpi_row(items) -> None:
    """Render a row of KPI metrics (stub)."""
    try:
        import streamlit as st
        cols = st.columns(len(items)) if items else []
        for col, (label, value) in zip(cols, items):
            col.metric(label, value)
    except ImportError:
        pass


__all__ = [
    "render_land_card",
    "render_metric_card",
    "render_land_table",
    "render_chat_bubble",
    "render_section_header",
    "render_kpi_row",
]
