# app.py

import os
import logging

from flask import Flask
from flask_login import LoginManager, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, close_db, init_db
from models import User
from routes.auth_routes import bp as auth_bp
from routes.chat_routes import bp as chat_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Adjust the logging level as needed (e.g., INFO, DEBUG)
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-default-secret-key")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        return User(user["id"], user["username"], user["email"])
    return None


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)

# Teardown database connection
app.teardown_appcontext(close_db)

# Initialize database
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
