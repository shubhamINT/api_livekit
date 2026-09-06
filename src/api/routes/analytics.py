from typing import Optional, Literal
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from src.api.dependencies import get_current_user
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import APIKey, CallRecord, UsageRecord
from src.core.db.usage_aggregations import usage_by_model_pipeline, usage_totals_pipeline
from src.core.logger import logger

router = APIRouter()


def _usage_dates(start_date, end_date):
    now = datetime.now(timezone.utc)
    return end_date or now, start_date or now - timedelta(days=30)


@router.get("/tokens/summary")
async def tokens_summary(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: APIKey = Depends(get_current_user),
):
    end_date, start_date = _usage_dates(start_date, end_date)
    match = {"user_email": current_user.user_email, "created_at": {"$gte": start_date, "$lte": end_date}}
    result = await UsageRecord.aggregate(usage_totals_pipeline(match)).to_list()
    summary = result[0] if result else {}
    summary.pop("_id", None)
    return apiResponse(success=True, message="Token usage summary fetched successfully", data=summary)


@router.get("/tokens/by-model")
async def tokens_by_model(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: APIKey = Depends(get_current_user),
):
    end_date, start_date = _usage_dates(start_date, end_date)
    match = {"user_email": current_user.user_email, "created_at": {"$gte": start_date, "$lte": end_date}}
    results = await UsageRecord.aggregate(usage_by_model_pipeline(match)).to_list()
    return apiResponse(success=True, message="Token usage by model fetched successfully", data={"models": results})


def _date_format_for_granularity(granularity: str) -> str:
    """Return MongoDB $dateToString format for the given granularity."""
    formats = {
        "day": "%Y-%m-%d",
        "week": "%Y-W%V",
        "month": "%Y-%m",
    }
    return formats.get(granularity, "%Y-%m-%d")


@router.get("/dashboard")
async def get_dashboard(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    current_user: APIKey = Depends(get_current_user),
):
    """At-a-glance analytics dashboard for the authenticated user."""
    logger.info(f"[analytics/dashboard] requested by {current_user.user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    match_filter = {
        "created_by_email": current_user.user_email,
        "started_at": {"$gte": start_date, "$lte": end_date},
    }

    try:
        # Summary aggregation
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": None,
                    "total_calls": {"$sum": 1},
                    "total_duration_minutes": {"$sum": {"$ifNull": ["$call_duration_minutes", 0]}},
                }
            },
        ]
        result = await CallRecord.aggregate(pipeline).to_list()
        summary = result[0] if result else {}

        # Period-based counts
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)

        period_pipeline = [
            {"$match": {"created_by_email": current_user.user_email}},
            {
                "$facet": {
                    "today": [
                        {"$match": {"started_at": {"$gte": today_start}}},
                        {"$count": "count"},
                    ],
                    "this_week": [
                        {"$match": {"started_at": {"$gte": week_start}}},
                        {"$count": "count"},
                    ],
                    "this_month": [
                        {"$match": {"started_at": {"$gte": month_start}}},
                        {"$count": "count"},
                    ],
                }
            },
        ]
        period_result = await CallRecord.aggregate(period_pipeline).to_list()
    except Exception as e:
        logger.error(f"[analytics/dashboard] failed for {current_user.user_email}: {e}")
        raise
    periods = period_result[0] if period_result else {}

    total_minutes = summary.get("total_duration_minutes", 0) or 0
    total_calls = summary.get("total_calls", 0) or 0

    return apiResponse(
        success=True,
        message="Dashboard analytics fetched successfully",
        data={
            "total_calls": total_calls,
            "total_duration_minutes": round(total_minutes, 2),
            "total_duration_hours": round(total_minutes / 60, 2),
            "avg_duration_minutes": round(total_minutes / total_calls, 2) if total_calls else 0,
            "calls_today": periods.get("today", [{}])[0].get("count", 0) if periods.get("today") else 0,
            "calls_this_week": periods.get("this_week", [{}])[0].get("count", 0) if periods.get("this_week") else 0,
            "calls_this_month": periods.get("this_month", [{}])[0].get("count", 0) if periods.get("this_month") else 0,
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        },
    )


@router.get("/calls/by-assistant")
async def get_calls_by_assistant(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    current_user: APIKey = Depends(get_current_user),
):
    """Per-assistant call count and duration breakdown."""
    logger.info(f"[analytics/calls/by-assistant] requested by {current_user.user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    try:
        pipeline = [
            {
                "$match": {
                    "created_by_email": current_user.user_email,
                    "started_at": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": {"assistant_id": "$assistant_id", "assistant_name": "$assistant_name"},
                    "total_calls": {"$sum": 1},
                    "total_duration_minutes": {"$sum": {"$ifNull": ["$call_duration_minutes", 0]}},
                }
            },
            {"$sort": {"total_duration_minutes": -1}},
            {
                "$project": {
                    "_id": 0,
                    "assistant_id": "$_id.assistant_id",
                    "assistant_name": "$_id.assistant_name",
                    "total_calls": 1,
                    "total_duration_minutes": {"$round": ["$total_duration_minutes", 2]},
                    "total_duration_hours": {"$round": [{"$divide": ["$total_duration_minutes", 60]}, 2]},
                    "avg_duration_minutes": {"$round": [{"$cond": [{"$eq": ["$total_calls", 0]}, 0, {"$divide": ["$total_duration_minutes", "$total_calls"]}]}, 2]},
                }
            },
        ]

        results = await CallRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[analytics/calls/by-assistant] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Calls by assistant fetched successfully",
        data={"assistants": results},
    )


@router.get("/calls/by-phone-number")
async def get_calls_by_phone_number(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    assistant_id: Optional[str] = Query(None, description="Filter by assistant"),
    current_user: APIKey = Depends(get_current_user),
):
    """Per phone number call count and duration breakdown — key for bill verification."""
    logger.info(f"[analytics/calls/by-phone-number] requested by {current_user.user_email}, assistant_id={assistant_id}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    match_filter = {
        "created_by_email": current_user.user_email,
        "started_at": {"$gte": start_date, "$lte": end_date},
    }
    if assistant_id:
        match_filter["assistant_id"] = assistant_id

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
                    "avg_duration_minutes": {"$round": [{"$cond": [{"$eq": ["$total_calls", 0]}, 0, {"$divide": ["$total_duration_minutes", "$total_calls"]}]}, 2]},
                }
            },
        ]

        results = await CallRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[analytics/calls/by-phone-number] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Calls by phone number fetched successfully",
        data={"phone_numbers": results},
    )


@router.get("/calls/by-time")
async def get_calls_by_time(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    granularity: Literal["day", "week", "month"] = Query("day", description="Time bucket granularity"),
    assistant_id: Optional[str] = Query(None, description="Filter by assistant"),
    current_user: APIKey = Depends(get_current_user),
):
    """Time-series call count and duration data."""
    logger.info(f"[analytics/calls/by-time] requested by {current_user.user_email}, granularity={granularity}, assistant_id={assistant_id}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    match_filter = {
        "created_by_email": current_user.user_email,
        "started_at": {"$gte": start_date, "$lte": end_date},
    }
    if assistant_id:
        match_filter["assistant_id"] = assistant_id

    date_format = _date_format_for_granularity(granularity)

    try:
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": date_format, "date": "$started_at"}},
                    "total_calls": {"$sum": 1},
                    "total_duration_minutes": {"$sum": {"$ifNull": ["$call_duration_minutes", 0]}},
                }
            },
            {"$sort": {"_id": 1}},
            {
                "$project": {
                    "_id": 0,
                    "date": "$_id",
                    "total_calls": 1,
                    "total_duration_minutes": {"$round": ["$total_duration_minutes", 2]},
                    "total_duration_hours": {"$round": [{"$divide": ["$total_duration_minutes", 60]}, 2]},
                }
            },
        ]

        results = await CallRecord.aggregate(pipeline).to_list()
    except Exception as e:
        logger.error(f"[analytics/calls/by-time] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Calls by time fetched successfully",
        data={"time_series": results, "granularity": granularity},
    )


@router.get("/calls/by-service")
async def get_calls_by_service(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    current_user: APIKey = Depends(get_current_user),
):
    """Per service (exotel/twilio/web) call count and duration breakdown."""
    logger.info(f"[analytics/calls/by-service] requested by {current_user.user_email}, date_range={start_date} to {end_date}")
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now
    if not start_date:
        start_date = now - timedelta(days=30)

    try:
        pipeline = [
            {
                "$match": {
                    "created_by_email": current_user.user_email,
                    "started_at": {"$gte": start_date, "$lte": end_date},
                }
            },
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
        logger.error(f"[analytics/calls/by-service] failed for {current_user.user_email}: {e}")
        raise

    return apiResponse(
        success=True,
        message="Calls by service fetched successfully",
        data={"services": results},
    )
