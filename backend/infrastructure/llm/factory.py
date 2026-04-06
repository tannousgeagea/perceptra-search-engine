import os
import logging
from typing import Optional
from infrastructure.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)

_client: Optional[BaseLLMClient] = None


def get_llm_client() -> BaseLLMClient:
    """Factory that returns the configured LLM client singleton.

    Reads LLM_PROVIDER env var to select the provider.
    Supported: 'anthropic', 'openai', 'ollama'.
    """
    global _client
    if _client is not None:
        return _client

    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("LLM_MODEL")

    if provider == "anthropic":
        from infrastructure.llm.anthropic_client import AnthropicLLMClient
        _client = AnthropicLLMClient(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=model or "claude-sonnet-4-20250514",
        )
    elif provider == "openai":
        from infrastructure.llm.openai_client import OpenAILLMClient
        _client = OpenAILLMClient(
            api_key=os.environ["OPENAI_API_KEY"],
            model=model or "gpt-4o",
        )
    elif provider == "ollama":
        from infrastructure.llm.ollama_client import OllamaLLMClient
        _client = OllamaLLMClient(
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=model or "llama3.1",
        )
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            "Supported providers: anthropic, openai, ollama"
        )

    logger.info(f"LLM client initialized: provider={provider}, model={_client._model}")
    return _client


def reset_llm_client() -> None:
    """Reset the cached client (useful for testing or config changes)."""
    global _client
    _client = None
