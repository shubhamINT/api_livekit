from typing import Optional, Literal
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from src.api.dependencies import get_super_admin
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import APIKey, CallRecord, UsageRecord
from src.core.logger import logger

router = APIRouter()


def _date_format_for_granularity(granularity: str) -> str:
    formats = {
        "day": "%Y-%m-%d",
        "week": "%Y-W%V",
        "month": "%Y-%m",
    }
    return formats.get(granularity, "%Y-%m-%d")


# --- Call Analytics (cross-tenant) ---


@router.get("/analytics/dashboard")
async def admin_dashboard(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    current_user: APIKey = Depends(get_super_admin),
):
    """Cross-tenant dashboard — summary of all calls across users."""
    logger.info(f"[admin/analytics/dashboard] requested by {current_user.user_email}, user_email_filter={user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    match_filter = {"started_at": {"$gte": start_date, "$lte": end_date}}
    if user_email:
        match_filter["created_by_email"] = user_email

    try:
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": None,
                    "total_calls": {"$sum": 1},
                    "total_duration_minutes": {"$sum": {"$ifNull": ["$call_duration_minutes", 0]}},
                    "unique_users": {"$addToSet": "$created_by_email"},
                }
            },
        ]
        result = await CallRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[admin/analytics/dashboard] failed for {current_user.user_email}: {e}")
        raise
    summary = result[0] if result else {}

    total_minutes = summary.get("total_duration_minutes", 0) or 0
    total_calls = summary.get("total_calls", 0) or 0

    return apiResponse(
        success=True,
        message="Admin dashboard fetched successfully",
        data={
            "total_calls": total_calls,
            "total_duration_minutes": round(total_minutes, 2),
            "total_duration_hours": round(total_minutes / 60, 2),
            "avg_duration_minutes": round(total_minutes / total_calls, 2) if total_calls else 0,
            "total_active_users": len(summary.get("unique_users", [])),
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        },
    )


@router.get("/analytics/calls/by-user")
async def admin_calls_by_user(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    current_user: APIKey = Depends(get_super_admin),
):
    """Per-user call count and duration breakdown — shows resource consumption per user."""
    logger.info(f"[admin/analytics/calls/by-user] requested by {current_user.user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    try:
        pipeline = [
            {"$match": {"started_at": {"$gte": start_date, "$lte": end_date}}},
            {
                "$group": {
                    "_id": "$created_by_email",
                    "total_calls": {"$sum": 1},
                    "total_duration_minutes": {"$sum": {"$ifNull": ["$call_duration_minutes", 0]}},
                }
            },
            {"$sort": {"total_duration_minutes": -1}},
            {
                "$project": {
                    "_id": 0,
                    "user_email": {"$ifNull": ["$_id", "unknown"]},
                    "total_calls": 1,
                    "total_duration_minutes": {"$round": ["$total_duration_minutes", 2]},
                    "total_duration_hours": {"$round": [{"$divide": ["$total_duration_minutes", 60]}, 2]},
                    "avg_duration_minutes": {"$round": [{"$cond": [{"$eq": ["$total_calls", 0]}, 0, {"$divide": ["$total_duration_minutes", "$total_calls"]}]}, 2]},
                }
            },
        ]

        results = await CallRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[admin/analytics/calls/by-user] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Calls by user fetched successfully",
        data={"users": results},
    )


@router.get("/analytics/calls/by-phone-number")
async def admin_calls_by_phone_number(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    current_user: APIKey = Depends(get_super_admin),
):
    """Cross-tenant phone number analytics."""
    logger.info(f"[admin/analytics/calls/by-phone-number] requested by {current_user.user_email}, user_email_filter={user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    match_filter = {"started_at": {"$gte": start_date, "$lte": end_date}}
    if user_email:
        match_filter["created_by_email"] = user_email

    try:
        platform_bucket_expr = {
            "$cond": [
                {"$or": [{"$eq": ["$call_type", "web"]}, {"$eq": ["$call_service", "web"]}]},
                "WEB_CALL",
                {"$ifNull": ["$platform_number", "UNKNOWN_PLATFORM"]},
            ]
        }
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": platform_bucket_expr,
                    "total_calls": {"$sum": 1},
                    "total_duration_minutes": {"$sum": {"$ifNull": ["$call_duration_minutes", 0]}},
                }
            },
            {"$sort": {"total_duration_minutes": -1}},
            {
                "$project": {
                    "_id": 0,
                    "phone_number": "$_id",
                    "total_calls": 1,
                    "total_duration_minutes": {"$round": ["$total_duration_minutes", 2]},
                    "total_duration_hours": {"$round": [{"$divide": ["$total_duration_minutes", 60]}, 2]},
                }
            },
        ]

        results = await CallRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[admin/analytics/calls/by-phone-number] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Calls by phone number fetched successfully",
        data={"phone_numbers": results},
    )


@router.get("/analytics/calls/by-service")
async def admin_calls_by_service(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    current_user: APIKey = Depends(get_super_admin),
):
    """Cross-tenant service breakdown (exotel/twilio/web totals)."""
    logger.info(f"[admin/analytics/calls/by-service] requested by {current_user.user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    try:
        pipeline = [
            {"$match": {"started_at": {"$gte": start_date, "$lte": end_date}}},
            {
                "$group": {
                    "_id": "$call_service",
                    "total_calls": {"$sum": 1},
                    "total_duration_minutes": {"$sum": {"$ifNull": ["$call_duration_minutes", 0]}},
                }
            },
            {"$sort": {"total_duration_minutes": -1}},
            {
                "$project": {
                    "_id": 0,
                    "service": {"$ifNull": ["$_id", "unknown"]},
                    "total_calls": 1,
                    "total_duration_minutes": {"$round": ["$total_duration_minutes", 2]},
                    "total_duration_hours": {"$round": [{"$divide": ["$total_duration_minutes", 60]}, 2]},
                }
            },
        ]

        results = await CallRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[admin/analytics/calls/by-service] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Calls by service fetched successfully",
        data={"services": results},
    )


# --- Token Usage Analytics (super-admin only) ---


@router.get("/analytics/tokens/summary")
async def admin_tokens_summary(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    assistant_id: Optional[str] = Query(None, description="Filter by assistant"),
    current_user: APIKey = Depends(get_super_admin),
):
    """Aggregated token and TTS usage across all users."""
    logger.info(f"[admin/analytics/tokens/summary] requested by {current_user.user_email}, user_email_filter={user_email}, assistant_id={assistant_id}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    match_filter = {"created_at": {"$gte": start_date, "$lte": end_date}}
    if user_email:
        match_filter["user_email"] = user_email
    if assistant_id:
        match_filter["assistant_id"] = assistant_id

    try:
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": None,
                    "total_records": {"$sum": 1},
                    "total_llm_input_audio_tokens": {"$sum": "$llm_input_audio_tokens"},
                    "total_llm_input_text_tokens": {"$sum": "$llm_input_text_tokens"},
                    "total_llm_input_image_tokens": {"$sum": "$llm_input_image_tokens"},
                    # Cached totals are a subset of the input totals above, not an
                    # addition to them — see UsageRecord in db_schemas.py.
                    "total_llm_input_cached_tokens": {"$sum": "$llm_input_cached_tokens"},
                    "total_llm_input_cached_audio_tokens": {"$sum": "$llm_input_cached_audio_tokens"},
                    "total_llm_input_cached_text_tokens": {"$sum": "$llm_input_cached_text_tokens"},
                    "total_llm_input_cached_image_tokens": {"$sum": "$llm_input_cached_image_tokens"},
                    "total_llm_input_cache_creation_tokens": {"$sum": "$llm_input_cache_creation_tokens"},
                    "total_llm_output_audio_tokens": {"$sum": "$llm_output_audio_tokens"},
                    "total_llm_output_text_tokens": {"$sum": "$llm_output_text_tokens"},
                    "total_llm_tokens": {"$sum": "$llm_total_tokens"},
                    "total_tts_characters": {"$sum": "$tts_characters_count"},
                    "total_tts_audio_duration": {"$sum": "$tts_audio_duration"},
                    # Token-billed providers only; zero for character/duration billing.
                    "total_tts_tokens": {"$sum": {"$add": ["$tts_input_tokens", "$tts_output_tokens"]}},
                    "total_stt_tokens": {"$sum": {"$add": ["$stt_input_tokens", "$stt_output_tokens"]}},
                    # Zero only in Gemini realtime, and only for duration-billed STT:
                    # token-billed providers report tokens instead.
                    "total_stt_audio_duration": {"$sum": "$stt_audio_duration"},
                    "total_call_duration_minutes": {"$sum": "$call_duration_minutes"},
                }
            },
        ]
        result = await UsageRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[admin/analytics/tokens/summary] failed for {current_user.user_email}: {e}")
        raise
    summary = result[0] if result else {}
    summary.pop("_id", None)

    return apiResponse(
        success=True,
        message="Token usage summary fetched successfully",
        data=summary,
    )


@router.get("/analytics/tokens/by-user")
async def admin_tokens_by_user(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    current_user: APIKey = Depends(get_super_admin),
):
    """Per-user token usage breakdown."""
    logger.info(f"[admin/analytics/tokens/by-user] requested by {current_user.user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    try:
        pipeline = [
            {"$match": {"created_at": {"$gte": start_date, "$lte": end_date}}},
            {
                "$group": {
                    "_id": "$user_email",
                    "total_calls": {"$sum": 1},
                    "total_llm_tokens": {"$sum": "$llm_total_tokens"},
                    "total_llm_input_audio_tokens": {"$sum": "$llm_input_audio_tokens"},
                    "total_llm_input_cached_tokens": {"$sum": "$llm_input_cached_tokens"},
                    "total_llm_input_cache_creation_tokens": {"$sum": "$llm_input_cache_creation_tokens"},
                    "total_llm_output_text_tokens": {"$sum": "$llm_output_text_tokens"},
                    "total_tts_characters": {"$sum": "$tts_characters_count"},
                    "total_tts_audio_duration": {"$sum": "$tts_audio_duration"},
                    "total_stt_audio_duration": {"$sum": "$stt_audio_duration"},
                    "total_call_duration_minutes": {"$sum": "$call_duration_minutes"},
                }
            },
            {"$sort": {"total_llm_tokens": -1}},
            {
                "$project": {
                    "_id": 0,
                    "user_email": "$_id",
                    "total_calls": 1,
                    "total_llm_tokens": 1,
                    "total_llm_input_audio_tokens": 1,
                    "total_llm_input_cached_tokens": 1,
                    "total_llm_input_cache_creation_tokens": 1,
                    "total_llm_output_text_tokens": 1,
                    "total_tts_characters": 1,
                    "total_tts_audio_duration": {"$round": ["$total_tts_audio_duration", 2]},
                    "total_stt_audio_duration": {"$round": ["$total_stt_audio_duration", 2]},
                    "total_call_duration_minutes": {"$round": ["$total_call_duration_minutes", 2]},
                    "total_call_duration_hours": {"$round": [{"$divide": ["$total_call_duration_minutes", 60]}, 2]},
                }
            },
        ]

        results = await UsageRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[admin/analytics/tokens/by-user] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Token usage by user fetched successfully",
        data={"users": results},
    )


@router.get("/analytics/tokens/by-assistant")
async def admin_tokens_by_assistant(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    current_user: APIKey = Depends(get_super_admin),
):
    """Per-assistant token usage breakdown."""
    logger.info(f"[admin/analytics/tokens/by-assistant] requested by {current_user.user_email}, user_email_filter={user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    match_filter = {"created_at": {"$gte": start_date, "$lte": end_date}}
    if user_email:
        match_filter["user_email"] = user_email

    try:
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": "$assistant_id",
                    "total_calls": {"$sum": 1},
                    "total_llm_tokens": {"$sum": "$llm_total_tokens"},
                    "total_llm_input_audio_tokens": {"$sum": "$llm_input_audio_tokens"},
                    "total_llm_input_cached_tokens": {"$sum": "$llm_input_cached_tokens"},
                    "total_llm_input_cache_creation_tokens": {"$sum": "$llm_input_cache_creation_tokens"},
                    "total_llm_output_text_tokens": {"$sum": "$llm_output_text_tokens"},
                    "total_tts_characters": {"$sum": "$tts_characters_count"},
                    "total_tts_audio_duration": {"$sum": "$tts_audio_duration"},
                    "total_stt_audio_duration": {"$sum": "$stt_audio_duration"},
                    "total_call_duration_minutes": {"$sum": "$call_duration_minutes"},
                }
            },
            {"$sort": {"total_llm_tokens": -1}},
            {
                "$project": {
                    "_id": 0,
                    "assistant_id": "$_id",
                    "total_calls": 1,
                    "total_llm_tokens": 1,
                    "total_llm_input_audio_tokens": 1,
                    "total_llm_input_cached_tokens": 1,
                    "total_llm_input_cache_creation_tokens": 1,
                    "total_llm_output_text_tokens": 1,
                    "total_tts_characters": 1,
                    "total_tts_audio_duration": {"$round": ["$total_tts_audio_duration", 2]},
                    "total_stt_audio_duration": {"$round": ["$total_stt_audio_duration", 2]},
                    "total_call_duration_minutes": {"$round": ["$total_call_duration_minutes", 2]},
                    "total_call_duration_hours": {"$round": [{"$divide": ["$total_call_duration_minutes", 60]}, 2]},
                }
            },
        ]

        results = await UsageRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[admin/analytics/tokens/by-assistant] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Token usage by assistant fetched successfully",
        data={"assistants": results},
    )
