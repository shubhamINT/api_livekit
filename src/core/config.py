import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings"""

    def __init__(self):
        self.PORT = int(os.getenv("PORT", "8000"))

        # MongoDB settings
        self.MONGODB_URL = os.getenv(
            "MONGODB_URL", "mongodb://admin:secretpassword@localhost:27017"
        )
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "livekit_db")

        # Email settings
        self.SMTP_HOST = os.getenv("SMTP_HOST", "smtp.sendgrid.net")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USER = os.getenv("SMTP_USER", "apikey")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
        self.FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@yourdomain.com")
        self.FROM_NAME = os.getenv("FROM_NAME", "Your App Name")

        # Logging settings
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
        self.LOG_JSON_FORMAT = os.getenv("LOG_JSON_FORMAT", "False").lower() == "true"
        self.LOG_FILE = os.getenv("LOG_FILE", "app.log")
        self.LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
        self.LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

        # LiveKit settings
        self.LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
        self.LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
        self.LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")

        # OpenAI settings
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

        # Cartesia settings
        self.CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")

        # Sarvam settings
        self.SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

        # Deepgram settings
        self.DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

        # ElevenLabs settings
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

        # Mistral settings
        self.MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

        # Google Gemini settings
        self.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

        # Audio Paths
        self.BASE_DIR = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.ASSETS_DIR = os.path.join(self.BASE_DIR, "assets")
        self.AUDIO_DIR = os.path.join(self.ASSETS_DIR, "audio")

        # AWS S3 Configuration
        self.AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
        self.AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self.AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
        self.S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
        self.S3_RECORDINGS_PREFIX = os.getenv("S3_RECORDINGS_PREFIX", "recordings/")
        self.S3_GREETING_PREFIX = os.getenv("S3_GREETING_PREFIX", "greeting_audio/")

        # Backend URL
        self.BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

        # ── Concurrency caps ────────────────────────────────────────────────────────
        # Split by call type because the types cost wildly different amounts. A phone call
        # needs an agent job process, a bridge process and an RTP port; a web call needs only
        # the agent job, and a text-only web call has no TTS, STT or VAD at all. One shared
        # counter meant a burst of web sessions could give phone callers a busy tone.
        #
        # MAX_CONCURRENT_JOBS keeps its name and its meaning as the telephony cap, so existing
        # deployments that set it keep the behaviour they tuned for.
        self.MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "12"))
        self.MAX_CONCURRENT_WEB_CALLS = int(os.getenv("MAX_CONCURRENT_WEB_CALLS", "40"))

        # Hard ceiling across every call type, so the two caps above can never together
        # exceed what the agent host can hold.
        #
        # NOT VERIFIED against a measured agent-session footprint — the only figure we have is
        # a ~238 MiB import floor per job process, before audio buffers, model state and
        # provider connections. Run a load test, read the agent container's steady-state RSS
        # per session with `docker stats`, and raise these with evidence.
        self.MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", "48"))

        # How many inbound INVITEs may be in setup at once. This is not a cap on live inbound
        # calls — the setup slot is released as soon as the call is answered. It has to exceed
        # the number of calls that can be ringing simultaneously, because the ring-until-ready
        # wait happens inside this semaphore.
        self.MAX_CONCURRENT_INVITE_SETUPS = int(os.getenv("MAX_CONCURRENT_INVITE_SETUPS", "24"))

        # End-of-call webhook. Read timeout is generous on purpose: the receiver often
        # writes the payload to its own database before answering, and a slow answer is
        # normal rather than a fault. Attempts covers transport errors, timeouts, 429 and
        # 5xx — never a 4xx, which the receiver has already decided about.
        self.END_CALL_WEBHOOK_TIMEOUT = float(os.getenv("END_CALL_WEBHOOK_TIMEOUT", "30"))
        self.END_CALL_WEBHOOK_ATTEMPTS = int(os.getenv("END_CALL_WEBHOOK_ATTEMPTS", "3"))

        # How long assistant create/update reuses one `GET /v1/models` answer per key
        # (src/core/model_support/openai_live.py). Lower it to notice an OpenAI model
        # retirement sooner; 0 disables the cache and asks on every write.
        self.OPENAI_MODEL_CACHE_TTL = float(os.getenv("OPENAI_MODEL_CACHE_TTL", "3600"))

settings = Settings()
