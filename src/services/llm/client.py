import json
from typing import Any, AsyncIterator, Optional
import httpx

from src.core.config import settings
from src.core.logger import logger


async def chat_completion(
    messages: list[dict[str, str]],
    provider: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Execute a non-streaming chat completion."""
    if provider == "openai":
        resolved_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
        if not resolved_key:
            raise ValueError("No API key configured for OpenAI")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }
        resolved_model = model or "gpt-5.4"
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            res = resp.json()
            choice = res["choices"][0]
            return {
                "message": choice["message"],
                "usage": res.get("usage", {}),
                "provider": provider,
                "model": resolved_model,
            }

    elif provider == "gemini":
        resolved_key = api_key or getattr(settings, "GOOGLE_API_KEY", None)
        if not resolved_key:
            raise ValueError("No API key configured for Gemini")

        resolved_model = model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:generateContent?key={resolved_key}"
        headers = {"Content-Type": "application/json"}

        # Map chat messages to Gemini contents format
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        payload = {"contents": contents}
        if temperature is not None:
            payload["generationConfig"] = {"temperature": temperature}
        if max_tokens is not None:
            payload.setdefault("generationConfig", {})["maxOutputTokens"] = max_tokens

        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            res = resp.json()
            candidates = res.get("candidates", [])
            text_out = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text_out = parts[0].get("text", "")

            usage_metadata = res.get("usageMetadata", {})
            return {
                "message": {"role": "assistant", "content": text_out},
                "usage": {
                    "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
                    "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
                    "total_tokens": usage_metadata.get("totalTokenCount", 0),
                },
                "provider": provider,
                "model": resolved_model,
            }
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


async def stream_chat_completion(
    messages: list[dict[str, str]],
    provider: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
) -> AsyncIterator[str]:
    """Stream chat completion tokens in SSE format."""
    if provider == "openai":
        resolved_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
        if not resolved_key:
            raise ValueError("No API key configured for OpenAI")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        }
        resolved_model = model or "gpt-5.4"
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        yield f"{line}\n\n"
                    else:
                        yield f"data: {line}\n\n"

    elif provider == "gemini":
        resolved_key = api_key or getattr(settings, "GOOGLE_API_KEY", None)
        if not resolved_key:
            raise ValueError("No API key configured for Gemini")

        resolved_model = model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:streamGenerateContent?alt=sse&key={resolved_key}"
        headers = {"Content-Type": "application/json"}

        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        payload = {"contents": contents}
        if temperature is not None:
            payload["generationConfig"] = {"temperature": temperature}

        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield f"{line}\n\n"
                yield "data: [DONE]\n\n"
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

