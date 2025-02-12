from flask import Blueprint, jsonify, request, current_app
from file_upload import FileUploadHandler
from models.uploaded_file import UploadedFile
import os
import requests
from config import config_instance
from functools import wraps
from typing import Dict, List, Optional
import json

def init_file_routes(app):
    """Initialize file upload routes"""
    file_routes = Blueprint('file_routes', __name__)
    file_handler = FileUploadHandler()

    def handle_azure_response(response: requests.Response) -> Dict:
        """Handle Azure API response and format errors."""
        try:
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = response.json().get('error', {}).get('message', 'Unknown error')
                return {
                    'error': f"Azure OpenAI API error: {error_msg}",
                    'status_code': response.status_code
                }
        except Exception as e:
            return {
                'error': f"Error processing Azure response: {str(e)}",
                'status_code': 500
            }

    def upload_to_azure(file_path: str, purpose: str = "fine-tune") -> Dict:
        """
        Upload a file to Azure OpenAI.

        Args:
            file_path (str): Path to the file to upload
            purpose (str): Purpose of the file (default: "fine-tune")

        Returns:
            Dict: Response from Azure OpenAI API
        """
        try:
            # Construct the Azure OpenAI API URL for file upload
            base_url = config_instance.AZURE_API_ENDPOINT
            if not base_url.endswith('/'):
                base_url += '/'
            url = f"{base_url}files?api-version={config_instance.AZURE_API_VERSION}"

            headers = {
                "api-key": config_instance.AZURE_OPENAI_KEY,
                "Content-Type": "multipart/form-data"
            }

            # Prepare the file for upload
            with open(file_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(file_path), f),
                    'purpose': (None, purpose)
                }

                response = requests.post(url, headers=headers, files=files)
                return handle_azure_response(response)

        except Exception as e:
            current_app.logger.error(f"Error uploading to Azure: {str(e)}")
            return {'error': str(e), 'status_code': 500}

    @file_routes.route('/upload/<chat_id>', methods=['POST'])
    def upload_files(chat_id: str):
        """
        Handle file upload with token tracking and enhanced validation.
        """
        from models.token_usage import TokenUsage
        from flask_login import current_user

        # Rate limit check
        try:
            if not TokenUsage.within_rate_limit(current_user.id, 60, 5000):
                return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
        except Exception as e:
            current_app.logger.error(f"Rate limit check failed: {str(e)}")

        try:
            # First use our existing handler to validate and save files locally
            result = file_handler.handle_upload(chat_id, user_id=current_user.id)

            if isinstance(result, tuple) and result[1] != 200:
                return result

            response_data = result.get_json()
            if not response_data.get('success'):
                return result

            saved_files = response_data['saved_files']

            # Try Azure operations only if configuration exists
            if hasattr(config_instance, 'AZURE_API_ENDPOINT') and config_instance.AZURE_API_ENDPOINT:
                try:
                    for file_info in saved_files:
                        file_path = os.path.join(config_instance.UPLOAD_FOLDER, chat_id, file_info['filename'])

                        # Upload to Azure OpenAI
                        azure_result = upload_to_azure(file_path)

                        if 'error' not in azure_result:
                            # Update the file info with Azure details
                            file_info.update({
                                'azure_file_id': azure_result.get('id'),
                                'azure_status': azure_result.get('status'),
                                'azure_purpose': azure_result.get('purpose'),
                                'content_type': 'text/plain'
                            })

                            # Update the database record with Azure file ID if it exists
                            azure_id = azure_result.get('id')
                            if azure_id:
                                UploadedFile.update_azure_file_id(
                                    file_info['id'],
                                    azure_id
                                )

                        # Cache text file content regardless of Azure upload result
                        try:
                            mime_type = file_info.get('mime_type', '')
                            if mime_type.startswith('text/') or mime_type == 'application/json':
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    cache_key = hash((file_info['filename'], os.path.getsize(file_path)))
                                    from chat_utils import context_manager
                                    context_manager.context_cache[cache_key] = [{"content": content}]
                        except Exception as e:
                            current_app.logger.warning(f"Failed to cache file content: {str(e)}")

                except Exception as e:
                    current_app.logger.error(f"Azure operations failed but continuing: {str(e)}")

            return jsonify({
                'success': True,
                'saved_files': saved_files,
                'message': f"Successfully uploaded {len(saved_files)} files",
                'total_size': response_data['total_size']
            })

        except Exception as e:
            current_app.logger.error(f"Error in file upload: {str(e)}")
            return jsonify({
                'error': f"File upload failed: {str(e)}",
                'status_code': 500
            }), 500

    @file_routes.route('/chunked-upload/<chat_id>', methods=['POST'])
    def chunked_upload(chat_id: str):
        """
        Handle chunked file uploads, merging multiple chunks into a single file.
        """
        from models.uploaded_file import UploadedFile
        from models.token_usage import TokenUsage
        from flask_login import current_user
        import os, uuid

        # Rate limit check
        try:
            if not TokenUsage.within_rate_limit(current_user.id, 60, 5000):
                return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
        except Exception as e:
            current_app.logger.error(f"Rate limit check failed: {str(e)}")

        # 1. Parse required form data
        chunk_index = int(request.form.get('chunkIndex', 0))
        total_chunks = int(request.form.get('totalChunks', 1))
        original_name = request.form.get('originalFilename', 'untitled')
        upload_id = request.form.get('uploadId') or str(uuid.uuid4())
        file_size = request.form.get('fileSize', type=int)

        # 2. Get the chunk data
        file_chunk = request.files.get('file')
        if not file_chunk:
            return jsonify({"error": "No chunk provided"}), 400

        # 3. Temporary storage directory
        temp_dir = os.path.join(config_instance.UPLOAD_FOLDER, 'temp_chunks', chat_id, upload_id)
        os.makedirs(temp_dir, exist_ok=True)

        # 4. Write chunk to a temporary file
        chunk_path = os.path.join(temp_dir, f"chunk_{chunk_index}")
        file_chunk.save(chunk_path)

        # 5. If this is the final chunk, merge them
        if chunk_index == total_chunks - 1:
            merged_filename = f"merged_{original_name}"
            merged_path = os.path.join(temp_dir, merged_filename)
            with open(merged_path, 'wb') as merged_file:
                for i in range(total_chunks):
                    part_path = os.path.join(temp_dir, f"chunk_{i}")
                    with open(part_path, 'rb') as part:
                        merged_file.write(part.read())

            # 6. Validate + transfer the merged file to final storage
            final_dest = os.path.join(config_instance.UPLOAD_FOLDER, chat_id)
            os.makedirs(final_dest, exist_ok=True)
            final_path = os.path.join(final_dest, merged_filename)
            os.rename(merged_path, final_path)

            # 8. Clean up temp chunks
            for i in range(total_chunks):
                os.remove(os.path.join(temp_dir, f"chunk_{i}"))

            return jsonify({
                "success": True,
                "uploadId": upload_id,
                "mergedFilename": merged_filename,
                "message": "All chunks merged successfully"
            })

        # For non-final chunks, just return success
        return jsonify({"success": True, "uploadId": upload_id})

    @file_routes.route('/files', methods=['GET'])
    def list_files():
        """
        List all files uploaded to Azure OpenAI.

        Returns:
            Response: A Flask JSON response with list of files.
        """
        try:
            url = f"{config_instance.AZURE_API_ENDPOINT}/files?api-version={config_instance.AZURE_API_VERSION}"
            headers = {"api-key": config_instance.AZURE_OPENAI_KEY}

            response = requests.get(url, headers=headers)
            result = handle_azure_response(response)

            if 'error' in result:
                return jsonify(result), result.get('status_code', 500)

            return jsonify({
                'success': True,
                'files': result.get('data', [])
            })

        except Exception as e:
            return jsonify({
                'error': f"Failed to list files: {str(e)}",
                'status_code': 500
            }), 500

    @file_routes.route('/files/<file_id>', methods=['DELETE'])
    def delete_file(file_id: str):
        """
        Delete a file from Azure OpenAI.

        Args:
            file_id (str): The ID of the file to delete.

        Returns:
            Response: A Flask JSON response indicating success or failure.
        """
        try:
            url = f"{config_instance.AZURE_API_ENDPOINT}/files/{file_id}?api-version={config_instance.AZURE_API_VERSION}"
            headers = {"api-key": config_instance.AZURE_OPENAI_KEY}

            response = requests.delete(url, headers=headers)
            result = handle_azure_response(response)

            if 'error' in result:
                return jsonify(result), result.get('status_code', 500)

            # Also delete local record if it exists
            UploadedFile.delete_by_azure_file_id(file_id)

            return jsonify({
                'success': True,
                'message': f"File {file_id} deleted successfully"
            })

        except Exception as e:
            return jsonify({
                'error': f"Failed to delete file: {str(e)}",
                'status_code': 500
            }), 500

    @file_routes.route('/preview/<int:file_id>', methods=['GET'])
    def preview_file(file_id: int):
         from flask import send_file, jsonify
         file_record = UploadedFile.get_by_id(file_id)
         if not file_record:
             return jsonify({"error": "File not found"}), 404
         return send_file(file_record.filepath, mimetype=file_record.mime_type)

    @file_routes.route('/contents/<int:file_id>', methods=['GET'])
    def get_file_contents(file_id: int):
        """
        Retrieve the contents of an uploaded file.
        """
        from flask_login import current_user
        from models.uploaded_file import UploadedFile

        try:
            # Get the file record
            file_record = UploadedFile.get_by_id(file_id)
            if not file_record:
                return jsonify({"error": "File not found"}), 404

            # Verify the user has access to this file
            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401

            # Check if the file exists
            if not os.path.exists(file_record.filepath):
                return jsonify({"error": "File content not found"}), 404

            # Read and return the file contents
            with open(file_record.filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            return jsonify({
                "success": True,
                "content": content,
                "mime_type": file_record.mime_type
            })

        except Exception as e:
            current_app.logger.error(f"Error retrieving file contents: {str(e)}")
            return jsonify({
                "error": "Failed to retrieve file contents",
                "details": str(e)
            }), 500

    # Register the blueprint with a URL prefix
    app.register_blueprint(file_routes, url_prefix='/api/files')
