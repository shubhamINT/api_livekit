"""S3 Storage Service for uploading recordings"""

import boto3
import os
from datetime import datetime
from src.core.logger import logger
from src.core.config import settings


class S3Service:
    """Service for uploading recordings to AWS S3"""

    def __init__(self):
        """Initialize S3 client with credentials from settings"""
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket_name = settings.S3_BUCKET_NAME
        self.prefix = getattr(settings, "S3_RECORDINGS_PREFIX", "recordings/")

    def upload_recording(self, local_file_path: str, room_name: str) -> str:
        """
        Upload recording to S3 with date-based folder structure

        Format: bucket/recordings/2026/02/11/roomname_timestamp.ogg

        Args:
            local_file_path: Path to the local recording file
            room_name: Name of the room (used in filename)

        Returns:
            S3 URL of the uploaded file

        Raises:
            Exception: If upload fails
        """
        try:
            # Generate S3 key with date folders
            now = datetime.utcnow()
            date_folder = now.strftime("%Y/%m/%d")
            timestamp = now.strftime("%H%M%S")
            filename = f"{room_name}_{timestamp}.ogg"
            s3_key = f"{self.prefix}{date_folder}/{filename}"

            logger.info(f"Uploading recording to S3: {self.bucket_name}/{s3_key}")

            # Upload file with metadata
            self.s3_client.upload_file(
                local_file_path,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    "ContentType": "audio/ogg",
                    "Metadata": {
                        "room-name": room_name,
                        "timestamp": now.isoformat(),
                        "uploaded-by": "livekit-agent",
                    },
                },
            )

            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            logger.info(f"✅ Successfully uploaded recording to {s3_url}")

            return s3_url

        except Exception as e:
            logger.error(f"❌ Failed to upload recording to S3: {e}")
            raise

    def delete_local_file(self, file_path: str):
        """
        Delete local file after successful S3 upload

        Args:
            file_path: Path to the local file to delete
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️  Deleted local recording file: {file_path}")
            else:
                logger.warning(f"⚠️  File not found for deletion: {file_path}")
        except Exception as e:
            logger.error(f"❌ Failed to delete local file {file_path}: {e}")

    def file_exists(self, s3_key: str) -> bool:
        """
        Check if a file exists in S3

        Args:
            s3_key: The S3 key to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except Exception:
            return False
