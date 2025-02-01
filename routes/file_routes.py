from flask import Blueprint, jsonify, request, current_app
from file_upload import FileUploadHandler
from models.uploaded_file import UploadedFile
import os
import requests
from config import Config
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
            base_url = Config.AZURE_API_ENDPOINT
            if not base_url.endswith('/'):
                base_url += '/'
            url = f"{base_url}files?api-version={Config.AZURE_API_VERSION}"

            headers = {
                "api-key": Config.AZURE_API_KEY,
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
        Handle file upload request with metadata and upload to Azure OpenAI.

        Args:
            chat_id (str): The chat ID associated with the uploaded files.

        Returns:
            Response: A Flask JSON response with detailed file metadata.
        """
        try:
            # First use our existing handler to validate and save files locally
            result = file_handler.handle_upload(chat_id)

            if isinstance(result, tuple) and result[1] != 200:
                return result

            response_data = result.get_json()
            if not response_data.get('success'):
                return result

            # Now upload each saved file to Azure OpenAI
            azure_files = []
            for file_info in response_data['saved_files']:
                file_path = os.path.join(Config.UPLOAD_FOLDER, chat_id, file_info['filename'])

                # Upload to Azure OpenAI
                azure_result = upload_to_azure(file_path)

                if 'error' in azure_result:
                    return jsonify({
                        'error': f"Azure upload failed for {file_info['filename']}: {azure_result['error']}",
                        'status_code': azure_result.get('status_code', 500)
                    }), azure_result.get('status_code', 500)

                # Update the file info with Azure details and content
                file_info.update({
                    'azure_file_id': azure_result.get('id'),
                    'azure_status': azure_result.get('status'),
                    'azure_purpose': azure_result.get('purpose'),
                    'content_type': 'text/plain'  # Default to text/plain for Azure OpenAI
                })

                # Cache the file content for quick access
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Cache using both local file ID and Azure file ID
                        cache_key = hash((file_info['filename'], os.path.getsize(file_path)))
                        azure_cache_key = hash(('azure', azure_result.get('id')))
                        from chat_utils import context_manager
                        context_manager.context_cache[cache_key] = content
                        context_manager.context_cache[azure_cache_key] = content
                except Exception as e:
                    current_app.logger.warning(f"Failed to cache file content: {str(e)}")

                # Update the database record with Azure file ID
                UploadedFile.update_azure_file_id(
                    file_info['id'],
                    azure_result.get('id')
                )

                azure_files.append(file_info)

            return jsonify({
                'success': True,
                'saved_files': azure_files,
                'message': f"Successfully uploaded {len(azure_files)} files to Azure OpenAI",
                'total_size': response_data['total_size']
            })

        except Exception as e:
            current_app.logger.error(f"Error in file upload: {str(e)}")
            return jsonify({
                'error': f"File upload failed: {str(e)}",
                'status_code': 500
            }), 500

    @file_routes.route('/files', methods=['GET'])
    def list_files():
        """
        List all files uploaded to Azure OpenAI.

        Returns:
            Response: A Flask JSON response with list of files.
        """
        try:
            url = f"{Config.AZURE_API_ENDPOINT}/files?api-version={Config.AZURE_API_VERSION}"
            headers = {"api-key": Config.AZURE_API_KEY}

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
            url = f"{Config.AZURE_API_ENDPOINT}/files/{file_id}?api-version={Config.AZURE_API_VERSION}"
            headers = {"api-key": Config.AZURE_API_KEY}

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

    # Register the blueprint with a URL prefix
    app.register_blueprint(file_routes, url_prefix='/api/files')
