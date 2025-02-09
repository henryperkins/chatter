from flask import Flask
from database import init_app, init_db
from config import Config


def create_app():
    app = Flask(__name__)
    config = Config()
    app.config['DATABASE_URI'] = config.DATABASE_URI
    app.config['ENCRYPTION_KEY'] = config.ENCRYPTION_KEY
    init_app(app)
    return app


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        init_db()

        # Now test the default model configuration
        from models.model import Model
        default_model = Model.get_default()
        if default_model:
            print('Default Model Configuration:')
            print(f'Name: {default_model.name}')
            print(f'Deployment: {default_model.deployment_name}')
            print(f'Endpoint: {default_model.api_endpoint}')
            print(f'API Version: {default_model.api_version}')
            print(f'Is Default: {default_model.is_default}')
            print(f'Requires o1 Handling: {default_model.requires_o1_handling}')
            print(f'Supports Streaming: {default_model.supports_streaming}')
            print(f'Max Completion Tokens: {default_model.max_completion_tokens}')
        else:
            print('No default model found')
