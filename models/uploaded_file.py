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
    azure_file_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def create(
        chat_id: str,
        filename: str,
        filepath: str,
        mime_type: Optional[str] = None,
        description: Optional[str] = None,
        azure_file_id: Optional[str] = None
    ) -> str:
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
                    (chat_id, filename, filepath, uuid, size, mime_type, description, version, azure_file_id, created_at, updated_at)
                    VALUES
                    (:chat_id, :filename, :filepath, :uuid, :size, :mime_type, :description, :version, :azure_file_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                    "version": new_version,
                    "azure_file_id": azure_file_id
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

    @staticmethod
    def update_azure_file_id(file_id: int, azure_file_id: str) -> bool:
        """
        Update the Azure file ID for an uploaded file.

        Args:
            file_id (int): The ID of the uploaded file
            azure_file_id (str): The Azure OpenAI file ID

        Returns:
            bool: True if successful, False otherwise
        """
        with db_session() as db:
            try:
                query = text("""
                    UPDATE uploaded_files
                    SET azure_file_id = :azure_file_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :file_id
                """)
                result = db.execute(query, {
                    "file_id": file_id,
                    "azure_file_id": azure_file_id
                })
                db.commit()
                success = result.rowcount > 0
                if success:
                    logger.info(f"Updated Azure file ID for file {file_id}")
                return success
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating Azure file ID: {e}")
                raise

    @staticmethod
    def delete_by_azure_file_id(azure_file_id: str) -> bool:
        """
        Delete an uploaded file by its Azure file ID.

        Args:
            azure_file_id (str): The Azure OpenAI file ID

        Returns:
            bool: True if successful, False otherwise
        """
        with db_session() as db:
            try:
                # First get file info for cleanup
                query = text("""
                    SELECT filepath, size FROM uploaded_files
                    WHERE azure_file_id = :azure_file_id
                """)
                file = db.execute(query, {"azure_file_id": azure_file_id}).first()

                if not file:
                    return False

                # Delete database record
                delete_query = text("""
                    DELETE FROM uploaded_files
                    WHERE azure_file_id = :azure_file_id
                """)
                db.execute(delete_query, {"azure_file_id": azure_file_id})
                db.commit()

                # Clean up file from disk
                filepath, size = file
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        logger.info(f"Deleted file {filepath} ({size} bytes)")
                except Exception as e:
                    logger.error(f"Failed to delete file {filepath}: {e}")

                return True

            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting file by Azure ID: {e}")
                raise

