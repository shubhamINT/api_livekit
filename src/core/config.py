import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings"""
    def __init__(self):
        self.PORT = int(os.getenv("PORT", "8000"))
        
        # MongoDB settings
        self.MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://admin:secretpassword@localhost:27017")
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
        self.LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760")) # 10MB
        self.LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

settings = Settings()
