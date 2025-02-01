import os
from dotenv import load_dotenv
from chat_api import get_azure_response
from models.uploaded_file import UploadedFile
from database import db_session, init_db
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def load_env():
    # Load environment variables from test.env
    load_dotenv('test.env')

    # Verify required variables
    required_vars = [
        'AZURE_API_KEY',
        'AZURE_API_ENDPOINT',
        'AZURE_API_VERSION',
        'AZURE_DEPLOYMENT_NAME'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

def test_file_handling():
    try:
        # Load environment variables
        load_env()

        # Initialize database
        init_db()

        # Test message
        messages = [{
            "role": "user",
            "content": "Please analyze the contents of the provided file."
        }]

        # Get configuration from environment
        deployment_name = os.getenv('AZURE_DEPLOYMENT_NAME')
        api_endpoint = os.getenv('AZURE_API_ENDPOINT')
        api_key = os.getenv('AZURE_API_KEY')
        api_version = os.getenv('AZURE_API_VERSION')

        logger.info(f"Using deployment: {deployment_name}")
        logger.info(f"Using endpoint: {api_endpoint}")
        logger.info(f"Using API version: {api_version}")

        # Create a test file record
        with db_session() as db:
            file_id = UploadedFile.create(
                chat_id='test-chat',
                filename='test_file.txt',
                filepath=os.path.abspath('test_file.txt'),
                azure_file_id='test-azure-file-id'  # This would normally come from Azure
            )
            logger.info(f"Created test file record with ID: {file_id}")

            # Get the file record
            file_record = UploadedFile.get_by_id(file_id)
            if not file_record:
                raise Exception("Failed to retrieve test file record")

            # Make API call with file reference
            response = get_azure_response(
                messages=messages,
                deployment_name=deployment_name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                api_version=api_version,
                file_ids=[file_record.azure_file_id]
            )

            logger.info("API Response:")
            logger.info(response)

            return response

    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

if __name__ == '__main__':
    test_file_handling()
