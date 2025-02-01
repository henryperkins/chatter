import os
from flask import send_file, jsonify, current_app
from flask_login import login_required
from models.uploaded_file import UploadedFile

def init_file_routes(app):
    @app.route('/file/<file_id>/preview', methods=['GET'])
    @login_required
    def preview_file(file_id):
        """
        Serve file content for preview.
        """
        try:
            # Get file record from database
            file_record = UploadedFile.get_by_id(file_id)
            if not file_record:
                return jsonify({"error": "File not found"}), 404

            # Verify file exists on disk
            if not os.path.exists(file_record.filepath):
                return jsonify({"error": "File not found on disk"}), 404

            # Get MIME type for response
            mime_type = file_record.mime_type or 'application/octet-stream'
            
            # Send file with proper MIME type
            return send_file(
                file_record.filepath,
                mimetype=mime_type,
                as_attachment=False,
                download_name=file_record.filename
            )

        except Exception as e:
            current_app.logger.error(f"Error serving file preview: {str(e)}")
            return jsonify({"error": "Failed to serve file"}), 500