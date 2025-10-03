from google.cloud import storage
from google.oauth2 import service_account
import os
from typing import Tuple, Optional
from core.config import settings
import logging

logger = logging.getLogger(__name__)

class StorageService:
    """Service for handling Google Cloud Storage operations"""

    ALLOWED_EXTENSIONS = {'.pdf', '.md', '.txt'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self):
        """Initialize GCS client with service account credentials"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                settings.gcp_sa_key_path
            )
            self.client = storage.Client(credentials=credentials)
            self.bucket_name = settings.gcp_storage_bucket_name
            self.bucket = self.client.bucket(self.bucket_name)
        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {str(e)}")
            raise

    def validate_file(self, filename: str, file_size: int) -> Tuple[bool, Optional[str]]:
        """
        Validate file extension and size

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file extension
        _, ext = os.path.splitext(filename)
        if ext.lower() not in self.ALLOWED_EXTENSIONS:
            return False, f"File type not allowed. Only {', '.join(self.ALLOWED_EXTENSIONS)} are accepted."

        # Check file size
        if file_size > self.MAX_FILE_SIZE:
            return False, f"File size exceeds maximum allowed size of {self.MAX_FILE_SIZE / 1024 / 1024}MB"

        return True, None

    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        room_id: str,
        content_type: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Upload file to GCS

        Args:
            file_content: File content as bytes
            filename: Original filename
            room_id: Room ID for organizing files
            content_type: MIME type of the file

        Returns:
            Tuple of (success, file_path, error_message)
        """
        try:
            # Validate file
            is_valid, error_msg = self.validate_file(filename, len(file_content))
            if not is_valid:
                return False, None, error_msg

            # Create file path: rooms/{room_id}/{filename}
            file_path = f"rooms/{room_id}/{filename}"

            # Upload to GCS
            blob = self.bucket.blob(file_path)
            blob.upload_from_string(file_content, content_type=content_type)

            logger.info(f"Successfully uploaded file {filename} to {file_path}")
            return True, file_path, None

        except Exception as e:
            logger.error(f"Failed to upload file {filename}: {str(e)}")
            return False, None, f"Upload failed: {str(e)}"

    def delete_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Delete file from GCS

        Args:
            file_path: Path to file in GCS

        Returns:
            Tuple of (success, error_message)
        """
        try:
            blob = self.bucket.blob(file_path)
            blob.delete()
            logger.info(f"Successfully deleted file {file_path}")
            return True, None
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {str(e)}")
            return False, f"Delete failed: {str(e)}"

    def get_file_url(self, file_path: str) -> str:
        """
        Get public URL for a file

        Args:
            file_path: Path to file in GCS

        Returns:
            Public URL string
        """
        return f"https://storage.googleapis.com/{self.bucket_name}/{file_path}"


# Singleton instance
storage_service = StorageService()
