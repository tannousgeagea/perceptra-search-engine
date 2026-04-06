import logging
from typing import List, Dict, Any
from anthropic import AsyncAnthropic
from infrastructure.llm.base import BaseLLMClient, ToolCall, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicLLMClient(BaseLLMClient):
    """Claude API implementation via the Anthropic SDK."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        tool_calls = [
            ToolCall(id=block.id, name=block.name, arguments=block.input)
            for block in response.content
            if block.type == "tool_use"
        ]
        text = next(
            (block.text for block in response.content if block.type == "text"),
            None,
        )

        return LLMResponse(tool_calls=tool_calls, text=text, raw_response=response)

    def format_tool_result(self, tool_call_id: str, result: str) -> Dict[str, Any]:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result,
                }
            ],
        }

    def format_assistant_message(self, response: LLMResponse) -> Dict[str, Any]:
        return {"role": "assistant", "content": response.raw_response.content}

    async def analyze_image(
        self,
        image_b64: str,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 1024,
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return response.content[0].text
