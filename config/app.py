"""
============================================================
Smart Land Management Copilot — Main Application (v3.0)
============================================================
Production-grade Streamlit application with clean architecture.

Layout:
  SIDEBAR         : Dashboard + Investor Matchmaking Form
  MAIN LEFT (40%) : Chat bot with GLM-5 Turbo
  MAIN RIGHT (60%): Interactive Folium map of Egypt

Architecture:
  app.py          → Composition root (10 lines of actual UI)
  ui/             → View layer (sidebar, chat, map, matchmaking)
  services/       → Business logic (RAG, GLM, matchmaking, map, analytics)
  data/           → Data access (repository pattern)
  models/         → Domain models (dataclasses)
  config/         → Configuration (settings)
============================================================
"""

import sys
import os
import logging

# Ensure project root is on the Python path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# Add project root (parent of config/) so imports like `services.` work
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# Also add parent directory explicitly for safety
PARENT_DIR = os.path.dirname(PROJECT_ROOT)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# ----------------------------------------------------------
# Logging Configuration
# ----------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(name)-20s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("app")

# ----------------------------------------------------------
# Imports (after path setup)
# ----------------------------------------------------------
import streamlit as st

from config.settings import get_settings
from services.state_manager import get_state
from ui.sidebar import render_sidebar
from ui.chat_view import render_chat_view
from ui.map_view import render_map_view
from ui.matchmaking_view import render_matchmaking_view


# ===========================================================
# CUSTOM CSS
# ===========================================================

def _load_custom_css() -> None:
    """Load the application's custom stylesheet."""
    css_path = os.path.join(PROJECT_ROOT, "styles", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ===========================================================
# MAIN ENTRY POINT
# ===========================================================

def main() -> None:
    """
    Application entry point.

    This function is the composition root — it initializes
    services, loads configuration, and delegates rendering
    to the appropriate view modules.
    """
    # Load and validate configuration
    settings = get_settings()
    logger.info(
        "Starting %s v%s (mock=%s, model=%s)",
        settings.app_name, settings.app_version,
        settings.mock_mode, settings.glm.model,
    )

    # Page configuration
    st.set_page_config(
        page_title="Smart Land Copilot — Egypt",
        page_icon="🏗️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Load custom CSS
    _load_custom_css()

    # Initialize session state
    state = get_state()

    # ----------------------------------------------------------
    # SIDEBAR
    # ----------------------------------------------------------
    with st.sidebar:
        render_sidebar()

    # ----------------------------------------------------------
    # MAIN CONTENT: Split Layout (40% chat | 60% map)
    # ----------------------------------------------------------
    left_col, right_col = st.columns([0.4, 0.6])

    with left_col:
        render_chat_view()

    with right_col:
        render_map_view()

    # ----------------------------------------------------------
    # MATCHMAKING REPORT (below main content)
    # ----------------------------------------------------------
    render_matchmaking_view()


if __name__ == "__main__":
    main()