
import os
from werkzeug.utils import secure_filename
from flask import current_app, request, jsonify
from typing import List, Dict, Tuple
from models.uploaded_file import UploadedFile

class FileUploadHandler:
    def __init__(self):
        self.ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'csv', 'py', 'js', 'md'}
        self.MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        self.MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB
        self.QUARANTINE_FOLDER = os.path.join(current_app.config['UPLOAD_FOLDER'], 'quarantine')
        self.SCAN_TIMEOUT = 30  # seconds for virus scan
        os.makedirs(self.QUARANTINE_FOLDER, exist_ok=True)

    def allowed_file(self, filename: str) -> bool:
        """Check if a file has an allowed extension."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS

    def validate_files(self, files: List) -> Tuple[List, List]:
        """Validate uploaded files with enhanced security checks."""
        valid_files = []
        errors = []
        file_hashes = set()

        # Check total size first
        total_size = sum(len(file.read()) for file in files)
        if total_size > self.MAX_TOTAL_SIZE:
            errors.append("Total size of files exceeds the limit (50MB).")
            return valid_files, errors

        for file in files:
            file.seek(0)
            
            # Basic validation
            if not self.allowed_file(file.filename):
                errors.append(f"File type not allowed: {file.filename}")
                continue
                
            file_size = len(file.read())
            if file_size > self.MAX_FILE_SIZE:
                errors.append(f"File too large: {file.filename}")
                continue
                
            file.seek(0)
            
            # Calculate file hash for deduplication
            file_hash = self.calculate_file_hash(file)
            if file_hash in file_hashes:
                errors.append(f"Duplicate file detected: {file.filename}")
                continue
            file_hashes.add(file_hash)
            
            # Verify file content matches extension
            if not self.validate_file_content(file):
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
        """Calculate SHA256 hash of file content."""
        import hashlib
        sha256_hash = hashlib.sha256()
        for byte_block in iter(lambda: file.read(4096), b""):
            sha256_hash.update(byte_block)
        file.seek(0)
        return sha256_hash.hexdigest()

    def validate_file_content(self, file) -> bool:
        """Verify file content matches its extension."""
        import magic
        file.seek(0)
        mime = magic.from_buffer(file.read(1024), mime=True)
        file.seek(0)
        
        # Map extensions to expected MIME types
        mime_map = {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'txt': 'text/plain',
            'csv': 'text/csv',
            'py': 'text/x-python',
            'js': 'application/javascript',
            'md': 'text/markdown'
        }
        
        ext = file.filename.split('.')[-1].lower()
        expected_mime = mime_map.get(ext, '')
        return mime.startswith(expected_mime)

    def scan_for_viruses(self, file) -> str:
        """Scan file for viruses using ClamAV."""
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
        """Move suspicious file to quarantine."""
        import shutil
        quarantine_path = os.path.join(self.QUARANTINE_FOLDER, file.filename)
        try:
            file.save(quarantine_path)
            current_app.logger.warning(f"File quarantined: {file.filename}")
        except Exception as e:
            current_app.logger.error(f"Failed to quarantine file: {str(e)}")

    def save_files(self, files: List, chat_id: str) -> List[Dict]:
        """Save validated files to the upload folder and database."""
        saved_files = []
        errors = []
        upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], chat_id)

        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)

        for file in files:
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_folder, filename)

            try:
                file.save(filepath)
                UploadedFile.create(chat_id, filename, filepath)
                saved_files.append({
                    'filename': filename,
                    'filepath': filepath,
                    'size': os.path.getsize(filepath)
                })
            except Exception as e:
                current_app.logger.error(f"Error saving file {filename}: {str(e)}")
                errors.append(f"Failed to save file: {filename}")

        if errors:
            current_app.logger.warning(f"Encountered errors while saving files: {errors}")

        return saved_files

    def handle_upload(self, chat_id: str):
        """Handle file upload request."""
        if 'files[]' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files[]')
        valid_files, errors = self.validate_files(files)

        if errors:
            return jsonify({'error': 'File validation failed', 'details': errors}), 400

        saved_files = self.save_files(valid_files, chat_id)
        return jsonify({
            'success': True,
            'saved_files': saved_files,
            'message': f"Successfully uploaded {len(saved_files)} files"
        })
