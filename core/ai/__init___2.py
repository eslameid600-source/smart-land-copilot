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
    from core.ai.llm.glm_client import *
    from core.ai.llm.ollama_service import *
    from core.ai.llm.router import *
except ImportError:
    pass

try:
    from core.ai.tft.model import *
    from core.ai.tft.training import *
    from core.ai.tft.airflow_dag import *
except ImportError:
    pass

__all__ = ['glm_client', 'ollama_service', 'tft', 'rag']