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

        # Backend URL
        self.BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


settings = Settings()
