"""Shared Gemini client configuration for API-key and Vertex AI runtimes."""

import os
import threading
import logging

from google import genai

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_client = None
_client_lock = threading.Lock()


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def get_gemini_model_id() -> str:
    return os.getenv("MODEL", "gemini-2.5-flash")


def _create_client():
    if env_flag("GOOGLE_GENAI_USE_VERTEXAI"):
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        if not project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT environment variable is required when "
                "GOOGLE_GENAI_USE_VERTEXAI is enabled"
            )
        logger.info(f"[GEMINI-CLIENT] Creating Vertex AI client (project={project_id}, location={location})")
        return genai.Client(vertexai=True, project=project_id, location=location)

    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        logger.info("[GEMINI-CLIENT] Creating API key client")
        return genai.Client(api_key=api_key)

    raise ValueError(
        "Gemini client is not configured. Set GOOGLE_API_KEY or enable "
        "GOOGLE_GENAI_USE_VERTEXAI with GOOGLE_CLOUD_PROJECT."
    )


def get_gemini_client():
    """Return a lazily-created Gemini client. Thread-safe, recreates if closed."""
    global _client
    with _client_lock:
        if _client is not None:
            try:
                if hasattr(_client, '_closed') and _client._closed:
                    logger.warning("[GEMINI-CLIENT] Client was closed, recreating...")
                    _client = _create_client()
                return _client
            except Exception:
                logger.warning("[GEMINI-CLIENT] Client check failed, recreating...")
                _client = _create_client()
                return _client
        _client = _create_client()
        return _client
