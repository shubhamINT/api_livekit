"""Shared MongoDB aggregation pipelines for usage analytics."""

_MODEL_TOTAL_FIELDS = {
    "total_estimated_cost_usd": ("estimated_cost_usd", "*"),
    "total_llm_input_audio_tokens": ("input_audio_tokens", "llm_usage"),
    "total_llm_input_text_tokens": ("input_text_tokens", "llm_usage"),
    "total_llm_input_image_tokens": ("input_image_tokens", "llm_usage"),
    "total_llm_input_cached_tokens": ("input_cached_tokens", "llm_usage"),
    "total_llm_input_cached_audio_tokens": ("input_cached_audio_tokens", "llm_usage"),
    "total_llm_input_cached_text_tokens": ("input_cached_text_tokens", "llm_usage"),
    "total_llm_input_cached_image_tokens": ("input_cached_image_tokens", "llm_usage"),
    "total_llm_input_cache_creation_tokens": ("input_cache_creation_tokens", "llm_usage"),
    "total_llm_output_audio_tokens": ("output_audio_tokens", "llm_usage"),
    "total_llm_output_text_tokens": ("output_text_tokens", "llm_usage"),
    "total_llm_tokens": ("total_tokens", "llm_usage"),
    "total_tts_characters": ("characters_count", "tts_usage"),
    "total_tts_audio_duration": ("audio_duration", "tts_usage"),
    "total_tts_input_tokens": ("input_tokens", "tts_usage"),
    "total_tts_output_tokens": ("output_tokens", "tts_usage"),
    "total_stt_input_tokens": ("input_tokens", "stt_usage"),
    "total_stt_output_tokens": ("output_tokens", "stt_usage"),
    "total_stt_audio_duration": ("audio_duration", "stt_usage"),
}

_FLAT_TOTAL_FIELDS = {
    "total_estimated_cost_usd": "estimated_cost_usd",
    "total_llm_input_audio_tokens": "llm_input_audio_tokens",
    "total_llm_input_text_tokens": "llm_input_text_tokens",
    "total_llm_input_image_tokens": "llm_input_image_tokens",
    "total_llm_input_cached_tokens": "llm_input_cached_tokens",
    "total_llm_input_cached_audio_tokens": "llm_input_cached_audio_tokens",
    "total_llm_input_cached_text_tokens": "llm_input_cached_text_tokens",
    "total_llm_input_cached_image_tokens": "llm_input_cached_image_tokens",
    "total_llm_input_cache_creation_tokens": "llm_input_cache_creation_tokens",
    "total_llm_output_audio_tokens": "llm_output_audio_tokens",
    "total_llm_output_text_tokens": "llm_output_text_tokens",
    "total_llm_tokens": "llm_total_tokens",
    "total_tts_characters": "tts_characters_count",
    "total_tts_audio_duration": "tts_audio_duration",
    "total_tts_tokens": None,
    "total_stt_tokens": None,
    "total_stt_audio_duration": "stt_audio_duration",
    "total_call_duration_minutes": "call_duration_minutes",
}


def usage_totals_pipeline(match: dict) -> list[dict]:
    """Preserve the existing flat summary response shape."""
    group = {"_id": None, "total_records": {"$sum": 1}}
    for output, field in _FLAT_TOTAL_FIELDS.items():
        if field:
            expression = {"$ifNull": [f"${field}", 0]}
        elif output == "total_tts_tokens":
            expression = {"$add": [{"$ifNull": ["$tts_input_tokens", 0]}, {"$ifNull": ["$tts_output_tokens", 0]}]}
        else:
            expression = {"$add": [{"$ifNull": ["$stt_input_tokens", 0]}, {"$ifNull": ["$stt_output_tokens", 0]}]}
        group[output] = {"$sum": expression}
    return [{"$match": match}, {"$group": group}]


def usage_by_model_pipeline(match: dict) -> list[dict]:
    """Group model usage by all attribution dimensions."""
    group = {
        "_id": {
            "type": "$model_usage.type",
            "provider": "$model_usage.provider",
            "model": "$model_usage.model",
        },
        "total_records": {"$sum": 1},
    }
    for output, (field, usage_type) in _MODEL_TOTAL_FIELDS.items():
        if field == "total_tokens":
            value = {"$add": [{"$ifNull": ["$model_usage.input_tokens", 0]}, {"$ifNull": ["$model_usage.output_tokens", 0]}]}
        else:
            value = {"$ifNull": [f"$model_usage.{field}", 0]}
        expression = (
            {"$ifNull": ["$model_usage.estimated_cost_usd", 0]}
            if usage_type == "*"
            else {"$cond": [{"$eq": ["$model_usage.type", usage_type]}, value, 0]}
        )
        group[output] = {"$sum": expression}
    return [
        {"$match": match},
        {"$unwind": "$model_usage"},
        {"$group": group},
        {"$sort": {"_id.type": 1, "_id.provider": 1, "_id.model": 1}},
        {
            "$project": {
                "_id": 0,
                "type": "$_id.type",
                "provider": "$_id.provider",
                "model": "$_id.model",
                "total_records": 1,
                **{field: 1 for field in _MODEL_TOTAL_FIELDS},
            }
        },
    ]
