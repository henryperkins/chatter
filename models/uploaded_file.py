import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
from werkzeug.utils import secure_filename

from sqlalchemy import text
from database import db_session

logger = logging.getLogger(__name__)


@dataclass
class UploadedFile:
    """
    Represents an uploaded file associated with a chat.
    """

    id: int
    chat_id: str
    filename: str
    filepath: str
    uuid: str
    size: int
    description: Optional[str] = None
    mime_type: Optional[str] = None
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def create(chat_id: str, filename: str, filepath: str, mime_type: Optional[str] = None, description: Optional[str] = None) -> str:
        """
        Insert a new uploaded file record into the database.
        Returns the unique file ID for reference.
        """
        with db_session() as db:
            try:
                # Check for existing versions
                version_query = text("""
                    SELECT MAX(version) FROM uploaded_files
                    WHERE chat_id = :chat_id AND filename = :filename
                """)
                result = db.execute(version_query, {
                    "chat_id": chat_id,
                    "filename": filename
                })
                current_version = result.scalar() or 0
                new_version = current_version + 1

                # Generate unique filename with UUID and version
                file_uuid = str(uuid.uuid4())
                base_name, ext = os.path.splitext(secure_filename(filename))
                unique_filename = f"{file_uuid}_{base_name}_v{new_version}{ext}"
                unique_filepath = os.path.join(os.path.dirname(filepath), unique_filename)

                # Move file to unique path
                os.rename(filepath, unique_filepath)

                # Get file size
                file_size = os.path.getsize(unique_filepath)

                # Insert new version
                query = text("""
                    INSERT INTO uploaded_files
                    (chat_id, filename, filepath, uuid, size, mime_type, description, version, created_at, updated_at)
                    VALUES
                    (:chat_id, :filename, :filepath, :uuid, :size, :mime_type, :description, :version, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """)
                result = db.execute(query, {
                    "chat_id": chat_id,
                    "filename": filename,
                    "filepath": unique_filepath,
                    "uuid": file_uuid,
                    "size": file_size,
                    "mime_type": mime_type,
                    "description": description,
                    "version": new_version
                })
                file_id = result.scalar()
                db.commit()
                logger.info(f"File uploaded: {filename} (v{new_version}) for chat {chat_id}")
                return file_id
            except Exception as e:
                db.rollback()
                # Clean up file if database operation failed
                if os.path.exists(unique_filepath):
                    os.remove(unique_filepath)
                logger.error(f"Failed to create uploaded file record: {e}")
                raise

    @staticmethod
    def get_by_id(file_id: int) -> Optional["UploadedFile"]:
        """
        Retrieve an uploaded file by its ID.
        """
        with db_session() as db:
            try:
                query = text("""
                    SELECT * FROM uploaded_files
                    WHERE id = :file_id
                """)
                row = db.execute(query, {"file_id": file_id}).mappings().first()
                if row:
                    return UploadedFile(**dict(row))
                return None
            except Exception as e:
                logger.error(f"Error retrieving uploaded file by ID: {e}")
                raise

    @staticmethod
    def get_by_chat_and_filename(chat_id: str, filename: str) -> Optional["UploadedFile"]:
        """
        Retrieve an uploaded file by chat ID and filename.
        """
        with db_session() as db:
            try:
                query = text("""
                    SELECT * FROM uploaded_files
                    WHERE chat_id = :chat_id AND filename = :filename
                """)
                row = db.execute(query, {
                    "chat_id": chat_id,
                    "filename": filename
                }).mappings().first()
                if row:
                    return UploadedFile(**dict(row))
                return None
            except Exception as e:
                logger.error(f"Error retrieving uploaded file: {e}")
                raise

    @staticmethod
    def delete_by_chat_ids(chat_ids: List[str]) -> Dict[str, int]:
        """
        Delete all uploaded files associated with specific chat IDs.
        Returns a dict with deletion stats.
        """
        if not chat_ids:
            return {"deleted_files": 0, "deleted_bytes": 0}

        with db_session() as db:
            try:
                # First get file info for cleanup
                query = text("""
                    SELECT filepath, size FROM uploaded_files
                    WHERE chat_id = ANY(:chat_ids)
                """)
                files = db.execute(query, {"chat_ids": chat_ids}).fetchall()

                # Delete database records
                delete_query = text("DELETE FROM uploaded_files WHERE chat_id = ANY(:chat_ids)")
                db.execute(delete_query, {"chat_ids": chat_ids})
                db.commit()

                # Clean up files from disk
                deleted_bytes = 0
                for filepath, size in files:
                    try:
                        if os.path.exists(filepath):
                            os.remove(filepath)
                            deleted_bytes += size
                    except Exception as e:
                        logger.error(f"Failed to delete file {filepath}: {e}")

                logger.info(f"Deleted {len(files)} files ({deleted_bytes} bytes) for chats: {', '.join(chat_ids)}")
                return {"deleted_files": len(files), "deleted_bytes": deleted_bytes}

            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting uploaded files: {e}")
                raise

