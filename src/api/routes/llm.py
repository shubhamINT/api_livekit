from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_current_user
from src.api.models.api_schemas.standalone import ChatCompletionRequest
from src.api.models.response_models import apiResponse
from src.api.routes.standalone_helper import log_standalone_usage, resolve_stage_config
from src.core.db.db_schemas import APIKey
from src.core.logger import logger
from src.services.llm.client import chat_completion, stream_chat_completion

router = APIRouter()


@router.post("/chat")
async def chat(
    request: ChatCompletionRequest,
    current_user: APIKey = Depends(get_current_user),
    x_provider_api_key: Optional[str] = Header(None, alias="X-Provider-API-Key"),
):
    """Execute conversational chat completions using OpenAI or Gemini."""
    stage_config = await resolve_stage_config(
        stage="llm",
        user=current_user,
        assistant_id=request.assistant_id,
        explicit_provider=request.provider,
        explicit_model=request.model,
        explicit_api_key=x_provider_api_key,
    )

    messages_payload = [{"role": m.role, "content": m.content} for m in request.messages]

    if request.stream:
        try:
            stream_gen = stream_chat_completion(
                messages=messages_payload,
                provider=stage_config["provider"],
                model=stage_config["model"],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                api_key=stage_config["api_key"],
            )
            return StreamingResponse(stream_gen, media_type="text/event-stream")
        except ValueError as ve:
            raise HTTPException(status_code=422, detail=str(ve))
        except Exception as exc:
            logger.error(f"LLM streaming error: {exc}")
            raise HTTPException(status_code=502, detail="Failed to initialize LLM stream")

    try:
        result = await chat_completion(
            messages=messages_payload,
            provider=stage_config["provider"],
            model=stage_config["model"],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            api_key=stage_config["api_key"],
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except httpx.HTTPStatusError as hse:
        logger.error(f"LLM provider HTTP error: {hse}")
        raise HTTPException(status_code=502, detail=f"Upstream LLM provider error: {hse.response.text}")
    except Exception as exc:
        logger.error(f"LLM unexpected error: {exc}")
        raise HTTPException(status_code=502, detail="Failed to generate completion from upstream provider")

    # Record usage & compute cost
    usage_raw = result.get("usage", {})
    prompt_tokens = usage_raw.get("prompt_tokens", 0)
    completion_tokens = usage_raw.get("completion_tokens", 0)
    total_tokens = usage_raw.get("total_tokens", prompt_tokens + completion_tokens)

    usage_info = await log_standalone_usage(
        stage="llm",
        user_email=current_user.user_email,
        provider=stage_config["provider"],
        model=stage_config["model"],
        assistant_id=stage_config["assistant_id"],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    result["usage"] = usage_info

    return apiResponse(success=True, message="Chat completion successful", data=result)

