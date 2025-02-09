from flask import Flask
from database import init_app
from models.model import Model
from config import Config


def create_app():
    app = Flask(__name__)
    config = Config()
    app.config['DATABASE_URI'] = config.DATABASE_URI
    app.config['ENCRYPTION_KEY'] = config.ENCRYPTION_KEY
    init_app(app)
    return app


def test_model_edit():
    # Get the default model
    default_model = Model.get_default()
    if not default_model:
        print('No default model found')
        return

    print('Original Configuration:')
    print(f'Name: {default_model.name}')
    print(f'Max Completion Tokens: {default_model.max_completion_tokens}')
    print(f'Supports Streaming: {default_model.supports_streaming}')
    print(f'Is Default: {default_model.is_default}')

    # Test updating model settings
    update_data = {
        'name': 'Updated Model Name',
        'max_completion_tokens': 8300,
        'supports_streaming': False,
        'is_default': True,  # Should maintain default status
        'provider_id': default_model.provider_id,  # Required for validation
        'deployment_name': default_model.deployment_name,  # Required for validation
        'api_endpoint': default_model.api_endpoint,  # Required for validation
        'api_key': default_model.api_key,  # Required for validation
        'model_type': default_model.model_type,  # Required for validation
    }

    try:
        Model.update(default_model.id, update_data)
        print('\nModel updated successfully')

        # Verify the changes
        updated_model = Model.get_by_id(default_model.id)
        print('\nUpdated Configuration:')
        print(f'Name: {updated_model.name}')
        print(f'Max Completion Tokens: {updated_model.max_completion_tokens}')
        print(f'Supports Streaming: {updated_model.supports_streaming}')
        print(f'Is Default: {updated_model.is_default}')

    except Exception as e:
        print(f'\nError updating model: {str(e)}')


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        test_model_edit()
