
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

    def allowed_file(self, filename: str) -> bool:
        """Check if a file has an allowed extension."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS

    def validate_files(self, files: List) -> Tuple[List, List]:
        """Validate uploaded files."""
        valid_files = []
        errors = []

        total_size = sum(len(file.read()) for file in files)
        if total_size > self.MAX_TOTAL_SIZE:
            errors.append("Total size of files exceeds the limit (50MB).")
            return valid_files, errors

        for file in files:
            file.seek(0)  # Reset file pointer after reading size
            if not self.allowed_file(file.filename):
                errors.append(f"File type not allowed: {file.filename}")
                continue
            if len(file.read()) > self.MAX_FILE_SIZE:
                errors.append(f"File too large: {file.filename}")
                continue
            file.seek(0)  # Reset file pointer for processing
            valid_files.append(file)

        return valid_files, errors

    def save_files(self, files: List, chat_id: str) -> List[Dict]:
        """Save validated files to the upload folder and database."""
        saved_files = []
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
