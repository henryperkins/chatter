import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
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
    uploaded_at: Optional[datetime] = None
    version: int = 1
    azure_file_id: Optional[str] = None
    azure_search_id: Optional[str] = None
    last_indexed_at: Optional[datetime] = None
    indexing_status: str = 'pending'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tokenized_text: Optional[str] = None

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
            unique_filepath = None
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
                    (chat_id, filename, filepath, uuid, size, mime_type, description, version,
                    azure_file_id, azure_search_id, indexing_status, last_indexed_at,
                    created_at, updated_at, tokenized_text)
                    VALUES
                    (:chat_id, :filename, :filepath, :uuid, :size, :mime_type, :description, :version,
                    :azure_file_id, NULL, 'pending', NULL,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL)
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
                # Clean up file if it was created and moved
                if unique_filepath and os.path.exists(unique_filepath):
                    try:
                        os.remove(unique_filepath)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to clean up file {unique_filepath}: {cleanup_error}")
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
    def update_search_status(file_id: int, status: str, search_id: Optional[str] = None) -> bool:
        """
        Update the Azure Search indexing status for a file.

        Args:
            file_id (int): The ID of the uploaded file
            status (str): The indexing status ('pending', 'indexed', 'failed')
            search_id (Optional[str]): The Azure Search document ID if indexed successfully

        Returns:
            bool: True if successful, False otherwise
        """
        with db_session() as db:
            try:
                query = text("""
                    UPDATE uploaded_files
                    SET indexing_status = :status,
                        azure_search_id = COALESCE(:search_id, azure_search_id),
                        last_indexed_at = CASE
                            WHEN :status = 'indexed' THEN CURRENT_TIMESTAMP
                            ELSE last_indexed_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :file_id
                """)
                result = db.execute(query, {
                    "file_id": file_id,
                    "status": status,
                    "search_id": search_id
                })
                db.commit()
                success = result.rowcount > 0
                if success:
                    logger.info(f"Updated Azure Search status to {status} for file {file_id}")
                return success
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating Azure Search status: {e}")
                raise

    @staticmethod
    def get_unindexed_files() -> List["UploadedFile"]:
        """
        Get all files that haven't been indexed in Azure Search.

        Returns:
            List[UploadedFile]: List of files with pending indexing status
        """
        with db_session() as db:
            try:
                query = text("""
                    SELECT * FROM uploaded_files
                    WHERE indexing_status = 'pending'
                    AND (mime_type LIKE 'text/%' OR mime_type IN ('application/json', 'text/markdown'))
                    ORDER BY created_at ASC
                """)
                rows = db.execute(query).mappings().all()
                return [UploadedFile(**dict(row)) for row in rows]
            except Exception as e:
                logger.error(f"Error retrieving unindexed files: {e}")
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

    @staticmethod
    def store_tokenized_content(file_id: int, tokenized_text: str) -> bool:
        """
        Save the tokenized version of an uploaded file's text in the DB.

        Args:
            file_id (int): The ID of the uploaded file
            tokenized_text (str): The tokenized content to store

        Returns:
            bool: True if successful, False otherwise
        """
        with db_session() as db:
            try:
                query = text("""
                    UPDATE uploaded_files
                    SET tokenized_text = :tokenized_text,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :file_id
                """)
                result = db.execute(query, {
                    "file_id": file_id,
                    "tokenized_text": tokenized_text
                })
                db.commit()
                success = result.rowcount > 0
                if success:
                    logger.info(f"Stored tokenized content for file {file_id}")
                return success
            except Exception as e:
                db.rollback()
                logger.error(f"Error storing tokenized content: {e}")
                raise
