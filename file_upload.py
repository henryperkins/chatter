import os
import os
from werkzeug.utils import secure_filename
from flask import current_app, request, jsonify
from typing import List, Dict, Tuple, Any
from models.uploaded_file import UploadedFile
from config import Config
from azure_search_config import AzureSearchConfig
import hashlib
import time


class FileUploadHandler:
    def __init__(self):
        """
        Initialize the file upload handler with centralized configuration.
        """
        self.config = Config()
        self.ALLOWED_EXTENSIONS = self.config.ALLOWED_FILE_EXTENSIONS
        self.MAX_FILE_SIZE = self.config.MAX_FILE_SIZE
        self.MAX_TOTAL_SIZE = self.config.MAX_TOTAL_FILE_SIZE
        self.QUARANTINE_FOLDER = os.path.join(self.config.UPLOAD_FOLDER, "quarantine")
        self.MIME_TYPE_MAP = self.config.MIME_TYPE_MAP
        self.SCAN_TIMEOUT = 30  # seconds for virus scan

        # Ensure the quarantine folder exists
        os.makedirs(self.QUARANTINE_FOLDER, exist_ok=True)

    def allowed_file(self, filename: str, file) -> Tuple[bool, List[str]]:
        """
        Check if a file has an allowed extension and MIME type.
        Returns a tuple of (is_allowed, errors) for better error reporting.

        Args:
            filename (str): The filename to check.
            file: The file object.

        Returns:
            Tuple[bool, List[str]]: (True, []) if allowed, (False, errors) if not
        """
        errors = []

        # Check filename security
        if not filename or filename.strip() == "":
            errors.append("Empty filename")
            return False, errors

        # Check extension
        if "." not in filename:
            errors.append("Missing file extension")
            return False, errors

        ext = filename.rsplit(".", 1)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            errors.append(f"File extension .{ext} not allowed")
            return False, errors

        # Check MIME type
        try:
            try:
                import magic
                file.seek(0)
                mime_type = magic.from_buffer(file.read(1024), mime=True)
                file.seek(0)
                current_app.logger.debug(f"Detected MIME type for {filename}: {mime_type}")
            except ImportError:
                # Fallback for when python-magic is not available
                current_app.logger.debug("python-magic not available, using extension-based detection")
                mime_type = self.MIME_TYPE_MAP.get(ext, 'application/octet-stream')

            # Special handling for Python files and other text-based files
            if ext == 'py' or mime_type == 'application/octet-stream' or ext == 'md':
                # Try to detect text content
                try:
                    file.seek(0)
                    sample = file.read(1024).decode('utf-8')
                    file.seek(0)
                    # If we can decode as UTF-8, treat as text
                    if ext == 'py':
                        mime_type = 'text/x-python'
                    elif ext in ['md', 'txt', 'json', 'js', 'css', 'html']:
                        mime_type = f'text/{ext}' if ext != 'md' else 'text/markdown'
                except (UnicodeDecodeError, Exception):
                    # Not text content, keep original mime type
                    if ext == 'py':
                        errors.append("Python file must be valid UTF-8 text")
                        return False, errors
                    pass

            if mime_type not in self.config.ALLOWED_MIME_TYPES and not any(
                mime_type.startswith(allowed_prefix)

                for allowed_prefix in ['text/', 'application/json']
            ):
                errors.append(f"MIME type {mime_type} not allowed")
                return False, errors

            # Verify MIME type matches extension for non-text files
            if not mime_type.startswith('text/'):
                expected_mime = self.MIME_TYPE_MAP.get(ext)
                if expected_mime and not mime_type.startswith(expected_mime):
                    errors.append(f"MIME type {mime_type} doesn't match extension .{ext}")
                    return False, errors

        except Exception as e:
            errors.append(f"Could not verify file type: {str(e)}")
            return False, errors

        return True, errors

    def validate_files(self, files: List) -> Tuple[List, List]:
        """
        Validate uploaded files with enhanced security checks.

        Args:
            files (List): List of uploaded file objects.

        Returns:
            Tuple[List, List]: A tuple containing valid files and a list of errors.
        """
        valid_files = []
        errors = []
        file_hashes = set()

        current_app.logger.debug(f"Starting validation of {len(files)} files")

        # Check total size first
        total_size = sum(len(file.read()) for file in files)
        current_app.logger.debug(f"Total size of all files: {total_size} bytes")

        if total_size > self.MAX_TOTAL_SIZE:
            msg = f"Total size of files exceeds the limit ({self.MAX_TOTAL_SIZE} bytes)."
            current_app.logger.error(msg)
            errors.append(msg)
            return valid_files, errors

        for file in files:
            file.seek(0)
            current_app.logger.debug(f"Validating file: {file.filename}")
            # Basic validation
            current_app.logger.debug(f"Starting validation for file: {file.filename}")
            is_allowed, validation_errors = self.allowed_file(file.filename, file)
            if not is_allowed:
                error_msg = f"File validation failed for {file.filename}: {validation_errors}"
                current_app.logger.error(error_msg)
                current_app.logger.debug(f"Allowed extensions: {self.config.ALLOWED_FILE_EXTENSIONS}")
                current_app.logger.debug(f"Allowed MIME types: {self.config.ALLOWED_MIME_TYPES}")
                errors.append(error_msg)
                continue

            file_size = len(file.read())
            current_app.logger.debug(f"File size: {file_size} bytes")

            if file_size > self.MAX_FILE_SIZE:
                error_msg = f"File too large: {file.filename} ({file_size} bytes) exceeds the {self.MAX_FILE_SIZE} byte limit."
                current_app.logger.error(error_msg)
                errors.append(error_msg)
                continue

            file.seek(0)

            # Calculate file hash for deduplication
            file_hash = self.calculate_file_hash(file)
            if file_hash in file_hashes:
                error_msg = f"Duplicate file detected: {file.filename}"
                current_app.logger.error(error_msg)
                errors.append(error_msg)
                continue
            file_hashes.add(file_hash)

            # Verify file content matches extension
            if not self.validate_file_content(file):
                ext = file.filename.split('.')[-1].lower()
                if ext not in ['txt', 'md']:
                    error_msg = f"File content doesn't match extension: {file.filename}"
                    current_app.logger.error(error_msg)
                    errors.append(error_msg)
                    continue

            # Scan for viruses
            scan_result = self.scan_for_viruses(file)
            if scan_result != "clean":
                error_msg = f"File rejected: {scan_result}"
                current_app.logger.error(error_msg)
                errors.append(error_msg)
                self.quarantine_file(file)
                continue

            file.seek(0)
            valid_files.append(file)
            current_app.logger.debug(f"File {file.filename} passed all validations")

        current_app.logger.debug(f"Validation complete. Valid files: {len(valid_files)}, Errors: {len(errors)}")
        return valid_files, errors

    def calculate_file_hash(self, file) -> str:
        """
        Calculate SHA256 hash of file content.

        Args:
            file: The file object.

        Returns:
            str: The SHA256 hash of the file content.
        """
        import hashlib

        sha256_hash = hashlib.sha256()
        for byte_block in iter(lambda: file.read(4096), b""):
            sha256_hash.update(byte_block)
        file.seek(0)
        return sha256_hash.hexdigest()

    def validate_file_content(self, file) -> bool:
        """
        Verify file content matches its extension with more lenient text file handling.

        Args:
            file: The file object.

        Returns:
            bool: True if the file content matches its extension, False otherwise.
        """
        file.seek(0)
        mime = None

        # Try python-magic first
        try:
            import magic
            mime = magic.from_buffer(file.read(1024), mime=True)
            current_app.logger.debug(f"MIME type detected using python-magic: {mime}")
        except (ImportError, Exception) as e:
            current_app.logger.warning(f"python-magic detection failed: {str(e)}")

        # If python-magic fails, try mimetypes module
        if not mime:
            try:
                import mimetypes
                ext = file.filename.split(".")[-1].lower()
                mime = mimetypes.guess_type(file.filename)[0]
                current_app.logger.debug(f"MIME type detected using mimetypes: {mime}")
            except Exception as e:
                current_app.logger.warning(f"mimetypes detection failed: {str(e)}")

        # Final fallback to extension-based detection
        if not mime:
            ext = file.filename.split(".")[-1].lower()
            mime = self.MIME_TYPE_MAP.get(ext, 'application/octet-stream')
            current_app.logger.debug(f"MIME type set from extension mapping: {mime}")

        file.seek(0)

        # Use MIME type map from centralized configuration
        mime_map = self.MIME_TYPE_MAP
        ext = file.filename.split(".")[-1].lower()

        # Special handling for Python files
        if ext == 'py':
            try:
                file.seek(0)
                content = file.read(1024).decode('utf-8')
                file.seek(0)
                current_app.logger.debug(f"Python file {file.filename} validated as UTF-8 text")
                return True
            except UnicodeDecodeError:
                current_app.logger.error(f"Python file {file.filename} is not valid UTF-8 text")
                return False

        # Special handling for markdown files
        if ext == 'md':
            try:
                file.seek(0)
                content = file.read(1024).decode('utf-8')
                file.seek(0)
                current_app.logger.debug(f"Markdown file {file.filename} validated as UTF-8 text")
                return True
            except UnicodeDecodeError:
                current_app.logger.error(f"Markdown file {file.filename} is not valid UTF-8 text")
                return False

        # Special handling for other text files
        if ext == 'txt' and mime.startswith('text/'):
            current_app.logger.debug(f"Text file {file.filename} validated")
            return True

        expected_mime = mime_map.get(ext, "")
        result = mime.startswith(expected_mime) if expected_mime else False
        current_app.logger.debug(f"File {file.filename} content validation result: {result} (expected: {expected_mime})")
        return result

    def scan_for_viruses(self, file) -> str:
        """
        Scan file for viruses using ClamAV if available.
        On Windows or if ClamAV is not installed, returns "clean".

        Args:
            file: The file object.

        Returns:
            str: "clean" if the file is clean or scan not available, otherwise the scan result.
        """
        try:
            import pyclamd
            import platform

            # Skip virus scan on Windows
            if platform.system() == 'Windows':
                return "clean"

            cd = pyclamd.ClamdUnixSocket()
            if not cd.ping():
                current_app.logger.warning("ClamAV daemon not running, skipping virus scan")
                return "clean"

            file.seek(0)
            scan_result = cd.scan_stream(file.read())
            file.seek(0)

            if scan_result is None:
                return "clean"
            return scan_result[1]
        except ImportError:
            current_app.logger.warning("pyclamd not installed, skipping virus scan")
            return "clean"
        except Exception as e:
            current_app.logger.warning(f"Virus scan skipped: {str(e)}")
            return "clean"

    def quarantine_file(self, file) -> None:
        """
        Move suspicious file to quarantine.

        Args:
            file: The file object.
        """
        quarantine_path = os.path.join(self.QUARANTINE_FOLDER, file.filename)
        try:
            file.save(quarantine_path)
            current_app.logger.warning(f"File quarantined: {file.filename}")
        except Exception as e:
            current_app.logger.error(f"Failed to quarantine file: {str(e)}")

    def index_file_in_search(self, file_info: Dict[str, Any]) -> None:
        """
        Index a file in Azure AI Search.

        Args:
            file_info: Dictionary containing file metadata and content
        """
        try:
            search_config = AzureSearchConfig()

            # Generate a unique document ID
            doc_id = hashlib.sha256(
                f"{file_info['filepath']}_{file_info['size']}".encode()
            ).hexdigest()

            # Read file content
            with open(file_info['filepath'], 'r', encoding='utf-8') as f:
                content = f.read()

            # Create the search document
            document = {
                "id": doc_id,
                "title": file_info['filename'],
                "content": content,
                "filepath": file_info['filepath'],
                "last_accessed": time.time(),
                "mime_type": file_info['mime_type'],
                "size": file_info['size'],
                "description": file_info.get('description', '')
            }

            # Index the document
            search_config.index_document(document)
            current_app.logger.info(f"Successfully indexed file {file_info['filename']} in Azure Search")

        except Exception as e:
            current_app.logger.error(f"Failed to index file in Azure Search: {str(e)}")
            raise

    def save_files(self, files: List, chat_id: str, descriptions: Dict[str, str] = None) -> List[Dict]:
        """
        Save validated files to the upload folder and database with metadata.
        Uses context management for optimized file handling and token tracking.

        Args:
            files (List): List of validated file objects.
            chat_id (str): The chat ID associated with the files.
            descriptions (Dict[str, str]): Optional mapping of filenames to descriptions.

        Returns:
            List[Dict]: A list of dictionaries containing saved file details.
        """
        from chat_utils import context_manager, context_monitor

        saved_files = []
        errors = []
        upload_folder = os.path.join(self.config.UPLOAD_FOLDER, chat_id)
        descriptions = descriptions or {}

        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)

        total_tokens = 0
        for file in files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_folder, filename)
            description = descriptions.get(filename)

            try:
                # Get MIME type with robust fallback mechanism
                file.seek(0)
                mime_type = None

                # Try python-magic first
                try:
                    import magic
                    mime_type = magic.from_buffer(file.read(1024), mime=True)
                    current_app.logger.debug(f"MIME type detected using python-magic: {mime_type}")
                except (ImportError, Exception) as e:
                    current_app.logger.warning(f"python-magic detection failed: {str(e)}")

                # If python-magic fails, try mimetypes module
                if not mime_type:
                    try:
                        import mimetypes
                        ext = filename.rsplit(".", 1)[1].lower()
                        mime_type = mimetypes.guess_type(filename)[0]
                        current_app.logger.debug(f"MIME type detected using mimetypes: {mime_type}")
                    except Exception as e:
                        current_app.logger.warning(f"mimetypes detection failed: {str(e)}")

                # Final fallback to extension-based detection
                if not mime_type:
                    ext = filename.rsplit(".", 1)[1].lower()
                    mime_type = self.MIME_TYPE_MAP.get(ext, 'application/octet-stream')
                    current_app.logger.debug(f"MIME type set from extension mapping: {mime_type}")

                file.seek(0)

                # Save file with progress tracking
                total_size = file.content_length or 0
                bytes_written = 0
                chunk_size = 8192  # 8KB chunks

                with open(filepath, 'wb') as f:
                    while True:
                        chunk = file.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_written += len(chunk)
                        if total_size > 0:
                            progress = (bytes_written / total_size) * 100
                            current_app.logger.debug(f"Upload progress for {filename}: {progress:.1f}%")

                # Handle content based on file type
                content = ""
                compressed_content = ""
                file_tokens = 0
                if mime_type.startswith('text/') or mime_type in ['application/json', 'text/markdown']:
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()

                        # Use context monitor for compression only on text files
                        compressed_content = context_monitor.compress_file_content(
                            content,
                            context_monitor.calculate_optimal_window_size(len(content))
                        )

                        # Only count tokens for text files
                        file_tokens = len(compressed_content.split())

                    except UnicodeDecodeError:
                        current_app.logger.warning(f"Could not read {filename} as text, skipping content processing")
                else:
                    current_app.logger.debug(f"Skipping content processing for binary file: {filename}")

                    # For binary files, use a token estimation based on file size
                    file_tokens = os.path.getsize(filepath) // 4  # Rough estimate

                total_tokens += file_tokens
                context_monitor.track_token_usage(file_tokens)

                # Create database record
                file_id = UploadedFile.create(
                    chat_id=chat_id,
                    filename=filename,
                    filepath=filepath,
                    mime_type=mime_type,
                    description=description
                )

                file_info = {
                    "id": file_id,
                    "filename": filename,
                    "filepath": filepath,
                    "size": os.path.getsize(filepath),
                    "mime_type": mime_type,
                    "description": description,
                    "token_count": file_tokens,
                    "is_truncated": len(compressed_content) < len(content)
                }

                saved_files.append(file_info)

                # Cache the processed content
                cache_key = hash((filename, os.path.getsize(filepath)))
                context_manager.context_cache[cache_key] = compressed_content

                # Index the file in Azure AI Search
                if mime_type.startswith('text/') or mime_type in ['application/json', 'text/markdown']:
                    try:
                        self.index_file_in_search(file_info)
                    except Exception as index_error:
                        current_app.logger.error(f"Failed to index file in Azure Search: {str(index_error)}")
                        # Don't fail the upload if indexing fails
                        pass

            except Exception as e:
                current_app.logger.error(f"Error saving file {filename} to {filepath}: {str(e)}")
                errors.append(f"Failed to save file: {filename}")
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception as cleanup_error:
                        current_app.logger.error(f"Failed to clean up file {filepath}: {cleanup_error}")

        if errors:
            current_app.logger.warning(f"Encountered errors while saving files: {errors}")

        # Update compression ratio based on total tokens
        if total_tokens > 0:
            context_monitor.optimize_compression()

        return saved_files

    def handle_upload(self, chat_id: str):
        """
        Handle file upload request with metadata.

        Args:
            chat_id (str): The chat ID associated with the uploaded files.

        Returns:
            Response: A Flask JSON response with detailed file metadata.
        """
        try:
            if "files[]" not in request.files:
                return jsonify({"error": "No files provided"}), 400

            # Get files and their descriptions
            files = request.files.getlist("files[]")
            descriptions = {}

            # Parse file descriptions from form data
            for key, value in request.form.items():
                if key.startswith('description_'):
                    filename = key.replace('description_', '')
                    descriptions[filename] = value

            # Log incoming files for debugging
            for file in files:
                current_app.logger.debug(f"Processing file: {file.filename}")
                if hasattr(file, 'content_type'):
                    current_app.logger.debug(f"Content type from request: {file.content_type}")

            valid_files, errors = self.validate_files(files)

            if errors:
                current_app.logger.error(f"File validation errors: {errors}")
                return jsonify({
                    "error": "File validation failed",
                    "details": errors,
                    "validation_info": {
                        "allowed_extensions": list(self.ALLOWED_EXTENSIONS),
                        "allowed_mime_types": list(self.config.ALLOWED_MIME_TYPES)
                    }
                }), 400

            saved_files = self.save_files(valid_files, chat_id, descriptions)

            # Enhance response with more metadata
            response_files = []
            for file_info in saved_files:
                file_data = {
                    "id": file_info["id"],
                    "filename": file_info["filename"],
                    "size": file_info["size"],
                    "mime_type": file_info["mime_type"],
                    "description": file_info["description"],
                    "upload_time": file_info.get("created_at", "")
                }
                response_files.append(file_data)

            return jsonify({
                "success": True,
                "saved_files": response_files,
                "message": f"Successfully uploaded {len(saved_files)} files",
                "total_size": sum(f["size"] for f in saved_files)
            })

        except Exception as e:
            current_app.logger.error(f"Error in handle_upload: {str(e)}", exc_info=True)
            return jsonify({
                "error": "File upload failed",
                "details": str(e)
            }), 500
