import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from infrastructure.llm.base import BaseLLMClient, ToolCall, LLMResponse

logger = logging.getLogger(__name__)


class OpenAILLMClient(BaseLLMClient):
    """OpenAI / ChatGPT implementation via the OpenAI SDK."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        # Convert provider-neutral (Anthropic-style) tool schemas to OpenAI format
        openai_tools = [
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

        # OpenAI uses system message in the messages list
        openai_messages = [{"role": "system", "content": system_prompt}] + messages

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            tools=openai_tools,
            messages=openai_messages,
        )

        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return LLMResponse(
            tool_calls=tool_calls,
            text=choice.message.content,
            raw_response=response,
        )

    def format_tool_result(self, tool_call_id: str, result: str) -> Dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }

    def format_assistant_message(self, response: LLMResponse) -> Dict[str, Any]:
        msg = response.raw_response.choices[0].message
        result = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
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
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        })
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
