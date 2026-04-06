from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ToolCall:
    """Provider-neutral representation of an LLM tool call."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Provider-neutral LLM response."""
    tool_calls: List[ToolCall] = field(default_factory=list)
    text: Optional[str] = None
    raw_response: Any = None


class BaseLLMClient(ABC):
    """Abstract base for all LLM providers.

    Subclasses implement provider-specific API calls and message formatting
    while exposing a unified interface for tool-augmented chat.
    """

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Send messages with tool definitions, return structured response."""
        ...

    @abstractmethod
    def format_tool_result(
        self,
        tool_call_id: str,
        result: str,
    ) -> Dict[str, Any]:
        """Format a tool execution result as a message for the next turn."""
        ...

    @abstractmethod
    def format_assistant_message(
        self,
        response: LLMResponse,
    ) -> Dict[str, Any]:
        """Format the assistant's response as a message for conversation history."""
        ...

    @abstractmethod
    async def analyze_image(
        self,
        image_b64: str,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 1024,
    ) -> str:
        """Send a base64-encoded JPEG image + text prompt to the VLM.

        Returns the raw text response (typically JSON for structured inspection tasks).
        """
        ...
