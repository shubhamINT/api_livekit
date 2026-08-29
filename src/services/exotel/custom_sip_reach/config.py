"""
Configuration constants and validation for the Exotel SIP bridge.

All environment variables, codec constants, timeouts, and the startup
config validator live here.
"""

import os
from dotenv import load_dotenv
from src.core.logger import logger

load_dotenv(override=False)

# ─────────────────────────────────────────────────────────────────────────────
# SIP / Network Configuration
# ─────────────────────────────────────────────────────────────────────────────

EXOTEL_SIP_HOST = os.getenv("EXOTEL_SIP_HOST", "pstn.in1.exotel.com")
EXOTEL_SIP_PORT = int(os.getenv("EXOTEL_SIP_PORT", "5070"))

# Your server's PUBLIC / Elastic IP (used in Via + Contact SIP headers)
EXOTEL_CUSTOMER_IP = os.getenv("EXOTEL_CUSTOMER_IP", "")
EXOTEL_CUSTOMER_SIP_PORT = int(os.getenv("EXOTEL_CUSTOMER_SIP_PORT", "5061"))

# ⚠️  CRITICAL: must be your EC2 Elastic/Public IP — NOT 0.0.0.0 or a private IP.
# This goes into SDP c= so Exotel knows where to send RTP back.
EXOTEL_MEDIA_IP = os.getenv("EXOTEL_MEDIA_IP", "")

EXOTEL_CALLER_ID = os.getenv("EXOTEL_CALLER_ID", "08044319240")
EXOTEL_FROM_DOMAIN = os.getenv("EXOTEL_FROM_DOMAIN", "lokaviveka1m.pstn.exotel.com")

EXOTEL_AUTH_USERNAME = os.getenv("EXOTEL_AUTH_USERNAME")
EXOTEL_AUTH_PASSWORD = os.getenv("EXOTEL_AUTH_PASSWORD")

# ─────────────────────────────────────────────────────────────────────────────
# LiveKit Configuration
# ─────────────────────────────────────────────────────────────────────────────

LK_URL = os.getenv("LIVEKIT_URL")
LK_API_KEY = os.getenv("LIVEKIT_API_KEY")
LK_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# ─────────────────────────────────────────────────────────────────────────────
# RTP / Codec Constants
# ─────────────────────────────────────────────────────────────────────────────

# RTP port pool — MUST stay outside LiveKit SIP's range (10000-40000) and LiveKit RTC's range
# (50000-60000), or a bridge and LiveKit can end up bound to the same UDP port and audio goes
# to the wrong place. Safe range: 41000-49999. Open the range in your AWS Security Group for
# UDP before changing it here — the ports are useless if the firewall drops them.
#
# The pool steps by 2 (port+1 is reserved for RTCP), so the range below gives
# (END - START) / 2 concurrent calls: 41000-42000 is 500.
#
# Both spellings are read for backwards compatibility; SIP_BRIDGE_PORT_RANGE_* wins if set.
RTP_PORT_START = int(
    os.getenv("SIP_BRIDGE_PORT_RANGE_START", os.getenv("RTP_PORT_START", "41000"))
)
RTP_PORT_END = int(
    os.getenv("SIP_BRIDGE_PORT_RANGE_END", os.getenv("RTP_PORT_END", "42000"))
)

RTP_HEADER_SIZE = 12
PCMU_PAYLOAD_TYPE = 0
PCMA_PAYLOAD_TYPE = 8
SAMPLE_RATE_SIP = 8000
SAMPLE_RATE_LK = 48000
MAX_FRAME_BUFFER = 2000  # ~20 seconds of 10ms LiveKit frames (10ms × 2000 = 20s)

# ─────────────────────────────────────────────────────────────────────────────
# Timeout Configuration
# ─────────────────────────────────────────────────────────────────────────────

NO_RTP_AFTER_ANSWER_SECONDS = int(os.getenv("NO_RTP_AFTER_ANSWER_SECONDS", "60"))
RTP_SILENCE_TIMEOUT_SECONDS = int(os.getenv("RTP_SILENCE_TIMEOUT_SECONDS", "30"))
INBOUND_SIP_LISTEN = os.getenv("INBOUND_SIP_LISTEN", "true").lower() in (
    "1",
    "true",
    "yes",
)

# Comma-separated list of trusted Exotel SIP IPs (empty = allow all, not recommended for production)
EXOTEL_SIP_ALLOWED_IPS: set[str] = set(
    filter(None, os.getenv("EXOTEL_SIP_ALLOWED_IPS", "").split(","))
)


# ─────────────────────────────────────────────────────────────────────────────
# Config Validation
# ─────────────────────────────────────────────────────────────────────────────


def validate_config() -> bool:
    """Check that all critical env vars are set.  Returns True when OK."""
    ok = True
    checks = [
        (
            EXOTEL_MEDIA_IP and EXOTEL_MEDIA_IP not in ("0.0.0.0", ""),
            "EXOTEL_MEDIA_IP must be your server's public/Elastic IP (NOT 0.0.0.0). "
            "Exotel uses this to route RTP back to you.",
        ),
        (
            EXOTEL_CUSTOMER_IP and EXOTEL_CUSTOMER_IP not in ("0.0.0.0", ""),
            "EXOTEL_CUSTOMER_IP must be your server's public/Elastic IP.",
        ),
        (bool(LK_URL), "LIVEKIT_URL is not set"),
        (bool(LK_API_KEY), "LIVEKIT_API_KEY is not set"),
        (bool(LK_API_SECRET), "LIVEKIT_API_SECRET is not set"),
    ]
    for passed, msg in checks:
        if not passed:
            logger.error(f"[CONFIG] ❌ {msg}")
            ok = False
    if ok:
        logger.debug(
            f"[CONFIG] ✅ public IP={EXOTEL_MEDIA_IP}, ports={RTP_PORT_START}-{RTP_PORT_END}"
        )
    return ok
