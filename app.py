"""Flask application initialization and configuration module.

This module sets up the Flask application, configures logging, initializes
Flask-Login, and registers blueprints for authentication, chat, and model routes.
"""

import logging
import os
from flask import Flask
from flask_login import LoginManager
from flask_socketio import SocketIO

from database import get_db, close_db, init_db, init_app
from models import User
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import bp as chat_bp
from routes.model_routes import bp as model_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
app.config.update(
    DATABASE="chat_app.db",
    SECRET_KEY=os.environ.get("SECRET_KEY", "your-default-secret-key"),
)

# Initialize database connection
init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(model_bp)

# Initialize database tables
with app.app_context():
    init_db()

# Initialize SocketIO
socketio = SocketIO(app)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Load user by ID for Flask-Login.

    Args:
        user_id: The user ID to load from the database

    Returns:
        User object if found, None otherwise
    """
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if user:
        return User(user["id"], user["username"], user["email"], user["role"])
    return None


# Teardown database connection
app.teardown_appcontext(close_db)

if __name__ == "__main__":
    socketio.run(app, debug=True)
