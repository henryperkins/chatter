import logging
from dataclasses import dataclass
from typing import Optional, List

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

    @staticmethod
    def create(chat_id: str, filename: str, filepath: str) -> str:
        """
        Insert a new uploaded file record into the database.
        Returns the unique file ID for reference.
        """
        with db_session() as db:
            try:
                # Generate unique filename with UUID
                file_uuid = str(uuid.uuid4())
                unique_filename = f"{file_uuid}_{secure_filename(filename)}"
                unique_filepath = os.path.join(os.path.dirname(filepath), unique_filename)
                
                # Move file to unique path
                os.rename(filepath, unique_filepath)
                
                query = text("""
                    INSERT INTO uploaded_files (chat_id, filename, filepath, uuid) 
                    VALUES (:chat_id, :filename, :filepath, :uuid)
                    RETURNING id
                """)
                result = db.execute(query, {
                    "chat_id": chat_id,
                    "filename": filename,
                    "filepath": unique_filepath,
                    "uuid": file_uuid
                }).fetchone()
                
                db.commit()
                logger.info(f"File uploaded: {filename} for chat {chat_id}")
                return result['id']
            except Exception as e:
                db.rollback()
                # Clean up file if database operation failed
                if os.path.exists(unique_filepath):
                    os.remove(unique_filepath)
                logger.error(f"Failed to create uploaded file record: {e}")
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
    def delete_by_chat_ids(chat_ids: List[str]) -> None:
        """
        Delete all uploaded files associated with specific chat IDs.
        """
        if not chat_ids:
            return
        with db_session() as db:
            try:
                placeholders = ",".join(f":id{i}" for i in range(len(chat_ids)))
                params = {f"id{i}": chat_id for i, chat_id in enumerate(chat_ids)}
                query = text(f"DELETE FROM uploaded_files WHERE chat_id IN ({placeholders})")
                db.execute(query, params)
                db.commit()
                logger.info("Deleted uploaded files for chats: %s", ", ".join(map(str, chat_ids)))
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting uploaded files: {e}")
                raise
