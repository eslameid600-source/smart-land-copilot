# ai package
"""
AI Module - LLM and ML Model Services
=====================================
- glm_client: GLM-5 Turbo via OpenRouter (Cloud-based)
- ollama_service: Local LLM via Ollama (Fallback)
- TFT: Temporal Fusion Transformer for time-series forecasting
- RAG: Retrieval-Augmented Generation for semantic search
"""

try:
    from core.ai.llm.glm_client import *  # noqa: F403
    from core.ai.llm.ollama_service import *  # noqa: F403
    from core.ai.llm.router import *  # noqa: F403
except ImportError:
    pass

try:
    from core.ai.tft.airflow_dag import *  # noqa: F403
    from core.ai.tft.model import *  # noqa: F403
    from core.ai.tft.training import *  # noqa: F403
except ImportError:
    pass

__all__ = ['glm_client', 'ollama_service', 'tft', 'rag']  # noqa: F405