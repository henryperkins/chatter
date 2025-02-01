import os
from werkzeug.utils import secure_filename
from flask import current_app, request, jsonify
from typing import List, Dict, Tuple
from models.uploaded_file import UploadedFile
from config import Config  # Import centralized configuration


class FileUploadHandler:
    def __init__(self):
        """
        Initialize the file upload handler with centralized configuration.
        """
        self.ALLOWED_EXTENSIONS = Config.ALLOWED_FILE_EXTENSIONS
        self.MAX_FILE_SIZE = Config.MAX_FILE_SIZE
        self.MAX_TOTAL_SIZE = Config.MAX_TOTAL_FILE_SIZE
        self.QUARANTINE_FOLDER = os.path.join(Config.UPLOAD_FOLDER, "quarantine")
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
            import magic
            file.seek(0)
            mime_type = magic.from_buffer(file.read(1024), mime=True)
            file.seek(0)

            # Special handling for text-based files that might be detected as octet-stream
            if mime_type == 'application/octet-stream':
                # Try to detect text content
                try:
                    file.seek(0)
                    sample = file.read(1024).decode('utf-8')
                    file.seek(0)
                    # If we can decode as UTF-8, treat as text
                    if ext in ['md', 'txt', 'json', 'py', 'js', 'css', 'html']:
                        mime_type = f'text/{ext}' if ext != 'md' else 'text/markdown'
                except (UnicodeDecodeError, Exception):
                    # Not text content, keep original mime type
                    pass

            if mime_type not in Config.ALLOWED_MIME_TYPES and not any(
                mime_type.startswith(allowed_prefix)
                for allowed_prefix in ['text/', 'application/json']
            ):
                errors.append(f"MIME type {mime_type} not allowed")
                return False, errors

            # Verify MIME type matches extension for non-text files
            if not mime_type.startswith('text/'):
                expected_mime = Config.MIME_TYPE_MAP.get(ext)
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

        # Check total size first
        total_size = sum(len(file.read()) for file in files)
        if total_size > self.MAX_TOTAL_SIZE:
            errors.append(
                f"Total size of files exceeds the limit ({self.MAX_TOTAL_SIZE} bytes)."
            )
            return valid_files, errors

        for file in files:
            file.seek(0)

            # Basic validation
            if not self.allowed_file(file.filename, file)[0]:
                errors.append(f"File type not allowed: {file.filename}")
                continue

            file_size = len(file.read())
            if file_size > self.MAX_FILE_SIZE:
                errors.append(
                    f"File too large: {file.filename} exceeds the {self.MAX_FILE_SIZE} byte limit."
                )
                continue

            file.seek(0)

            # Calculate file hash for deduplication
            file_hash = self.calculate_file_hash(file)
            if file_hash in file_hashes:
                errors.append(f"Duplicate file detected: {file.filename}")
                continue
            file_hashes.add(file_hash)

            # Verify file content matches extension
            if not self.validate_file_content(file) and file.filename.split('.')[-1].lower() not in ['txt', 'md']:
                errors.append(f"File content doesn't match extension: {file.filename}")
                continue

            # Scan for viruses
            scan_result = self.scan_for_viruses(file)
            if scan_result != "clean":
                errors.append(f"File rejected: {scan_result}")
                self.quarantine_file(file)
                continue

            file.seek(0)
            valid_files.append(file)

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
        import magic

        file.seek(0)
        mime = magic.from_buffer(file.read(1024), mime=True)
        file.seek(0)

        # Use MIME type map from centralized configuration
        mime_map = Config.MIME_TYPE_MAP

        ext = file.filename.split(".")[-1].lower()

        # Special handling for text files
        if ext in ['txt', 'md'] and mime.startswith('text/'):
            return True

        expected_mime = mime_map.get(ext, "")
        return mime.startswith(expected_mime) if expected_mime else False


    def scan_for_viruses(self, file) -> str:
        """
        Scan file for viruses using ClamAV.

        Args:
            file: The file object.

        Returns:
            str: "clean" if the file is clean, otherwise the scan result.
        """
        try:
            import pyclamd

            cd = pyclamd.ClamdUnixSocket()
            if not cd.ping():
                raise Exception("ClamAV daemon not running")

            file.seek(0)
            scan_result = cd.scan_stream(file.read())
            file.seek(0)

            if scan_result is None:
                return "clean"
            return scan_result[1]
        except Exception as e:
            current_app.logger.error(f"Virus scan failed: {str(e)}")
            return "scan_failed"

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
        upload_folder = os.path.join(Config.UPLOAD_FOLDER, chat_id)
        descriptions = descriptions or {}

        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)

        total_tokens = 0
        for file in files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_folder, filename)
            description = descriptions.get(filename)

            try:
                # Get MIME type
                file.seek(0)
                import magic
                mime_type = magic.from_buffer(file.read(1024), mime=True)
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

                # Read file content for context management
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Use context monitor for compression
                compressed_content = context_monitor.compress_file_content(
                    content,
                    context_monitor.calculate_optimal_window_size(len(content))
                )
                
                # Track token usage
                file_tokens = len(compressed_content.split())
                total_tokens += file_tokens
                context_monitor.track_token_usage(file_tokens)

                # Create database record with metadata
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
                cache_key = hash((filename, len(content)))
                context_manager.context_cache[cache_key] = compressed_content

            except Exception as e:
                current_app.logger.error(f"Error saving file {filename}: {str(e)}")
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

        valid_files, errors = self.validate_files(files)

        if errors:
            return jsonify({"error": "File validation failed", "details": errors}), 400

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
