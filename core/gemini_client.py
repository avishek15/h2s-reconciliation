"""Shared Gemini client configuration for API-key and Vertex AI runtimes."""

import os

from google import genai


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_client = None


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def get_gemini_model_id() -> str:
    return os.getenv("MODEL", "gemini-2.5-flash")


def get_gemini_client():
    """Return a lazily-created Gemini client matching the current deployment mode."""
    global _client
    if _client is not None:
        return _client

    if env_flag("GOOGLE_GENAI_USE_VERTEXAI"):
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        if not project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT environment variable is required when "
                "GOOGLE_GENAI_USE_VERTEXAI is enabled"
            )
        _client = genai.Client(vertexai=True, project=project_id, location=location)
        return _client

    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        _client = genai.Client(api_key=api_key)
        return _client

    raise ValueError(
        "Gemini client is not configured. Set GOOGLE_API_KEY or enable "
        "GOOGLE_GENAI_USE_VERTEXAI with GOOGLE_CLOUD_PROJECT."
    )
