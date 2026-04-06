import json
import logging
from typing import List, Dict, Any
import httpx
from infrastructure.llm.base import BaseLLMClient, ToolCall, LLMResponse

logger = logging.getLogger(__name__)


class OllamaLLMClient(BaseLLMClient):
    """Ollama implementation for local models via the /api/chat endpoint.

    Ollama supports tool calling for models like llama3.1, mistral, etc.
    Uses the native Ollama API (not OpenAI-compatible endpoint) for best
    tool calling support.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = httpx.AsyncClient(timeout=60.0)

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        # Convert provider-neutral tool schemas to Ollama/OpenAI function format
        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "tools": ollama_tools,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        resp = await self._http.post(f"{self._base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        message = data.get("message", {})
        tool_calls = []
        if message.get("tool_calls"):
            for i, tc in enumerate(message["tool_calls"]):
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                # Ollama may return arguments as a string or dict
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(
                    ToolCall(
                        id=f"ollama_{i}",
                        name=fn.get("name", ""),
                        arguments=args,
                    )
                )

        return LLMResponse(
            tool_calls=tool_calls,
            text=message.get("content"),
            raw_response=data,
        )

    def format_tool_result(self, tool_call_id: str, result: str) -> Dict[str, Any]:
        return {"role": "tool", "content": result}

    def format_assistant_message(self, response: LLMResponse) -> Dict[str, Any]:
        message = response.raw_response.get("message", {})
        result = {"role": "assistant", "content": message.get("content", "")}
        if message.get("tool_calls"):
            result["tool_calls"] = message["tool_calls"]
        return result

    async def analyze_image(
        self,
        image_b64: str,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 1024,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": prompt,
            "images": [image_b64],
        })
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data.get("message", {}).get("content", "")
