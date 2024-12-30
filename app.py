import os
import sqlite3
import uuid
import logging
import requests
import markdown2
from bs4 import BeautifulSoup
from conversation_manager import ConversationManager
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    g,
    flash,
)
from markupsafe import Markup
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

from azure_config import initialize_azure_client, initialize_client_from_model
from database import add_model, get_models, update_model, delete_model, get_default_model

# Initialize Azure client
client, deployment_name = initialize_azure_client()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
from conversation_manager import ConversationManager

# Initialize conversation manager
conversation_manager = ConversationManager()

# Initialize chat contexts dictionary
chat_contexts = {}

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # type: ignore

# Database configuration
DATABASE = "chat_app.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql", mode="r") as f:
            db.cursor().executescript(f.read())
        db.commit()

@app.cli.command("init-db")
def init_db_command():
    """Initialize the database."""
    init_db()
    print("Initialized the database.")


# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        return User(user["id"], user["username"], user["email"])
    return None


# Model management routes
@app.route("/models", methods=["GET"])
@login_required
def list_models():
    """List all models."""
    models = get_models()
    return jsonify([{
        "id": model["id"],
        "name": model["name"],
        "description": model["description"],
        "model_type": model["model_type"],
        "api_endpoint": model["api_endpoint"],
        "temperature": model["temperature"],
        "max_tokens": model["max_tokens"],
        "is_default": bool(model["is_default"])
    } for model in models])


@app.route("/models", methods=["POST"])
@login_required
def create_model():
    """Create a new model."""
    data = request.get_json()
    name = data.get("name")
    description = data.get("description", "")
    model_type = data.get("model_type", "azure")
    api_endpoint = data.get("api_endpoint")
    api_key = data.get("api_key")
    temperature = data.get("temperature", 1.0)
    max_tokens = data.get("max_tokens", 32000)
    is_default = data.get("is_default", False)
    
    if not name:
        return jsonify({"error": "Model name is required"}), 400
        
    add_model(
        name=name,
        description=description,
        model_type=model_type,
        api_endpoint=api_endpoint,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        is_default=is_default
    )
    return jsonify({"success": True})


@app.route("/models/<int:model_id>", methods=["PUT"])
@login_required
def update_model_route(model_id):
    """Update an existing model."""
    data = request.get_json()
    name = data.get("name")
    description = data.get("description", "")
    model_type = data.get("model_type")
    api_endpoint = data.get("api_endpoint")
    api_key = data.get("api_key")
    temperature = data.get("temperature")
    max_tokens = data.get("max_tokens")
    is_default = data.get("is_default")
    
    if not name:
        return jsonify({"error": "Model name is required"}), 400
        
    update_model(
        model_id=model_id,
        name=name,
        description=description,
        model_type=model_type,
        api_endpoint=api_endpoint,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        is_default=is_default
    )
    return jsonify({"success": True})


@app.route("/models/<int:model_id>", methods=["DELETE"])
@login_required
def delete_model_route(model_id):
    """Delete a model."""
    delete_model(model_id)
    return jsonify({"success": True})


def search_web(query):
    """Perform a web search and return formatted results."""
    try:
        # Perform search and get results
        results = []  # This should be replaced with actual search implementation
        
        formatted_results = []
        for idx, result in enumerate(results[:3], 1):
            formatted_result = f"### {idx}. {result['title']}\n"
            formatted_result += f"{result['snippet']}\n"
            if result.get("url"):
                formatted_result += f"[Read more]({result['url']})\n"
            formatted_results.append(formatted_result)

        return (
            "\n\n".join(formatted_results)
            if formatted_results
            else "No relevant results found."
        )
    except requests.Timeout:
        return "The search request timed out. Please try again."
    except requests.RequestException as e:
        print(f"Search error: {str(e)}")
        return "An error occurred while performing the search. Please try again later."
    except Exception as e:
        print(f"Unexpected error during search: {str(e)}")
        return "An unexpected error occurred while processing your search request."

if __name__ == "__main__":
    app.run(debug=True)


# Initialize database
with app.app_context():
    init_db()


# Authentication routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat_interface"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required")
            return render_template("login.html")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            user_obj = User(user["id"], user["username"], user["email"])
            login_user(user_obj)
            return redirect(url_for("chat_interface"))

        flash("Invalid username or password")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat_interface"))

    if request.method == "POST":
        username = request.form.get("username", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        if not all([username, email, password]):
            flash("All fields are required")
            return render_template("register.html")

        db = get_db()
        if db.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone():
            flash("Username already exists")
            return render_template("register.html")

        if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            flash("Email already registered")
            return render_template("register.html")

        db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, generate_password_hash(password)),
        )
        db.commit()

        flash("Registration successful! Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# File upload route
@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    logger.debug("Received file upload request")
    if "files" not in request.files:
        logger.warning("No files part in the request")
        return jsonify({"error": "No files part"}), 400

    logger.debug("Processing uploaded files")

    files = request.files.getlist("files")
    if len(files) > 4:
        logger.warning("User attempted to upload more than 4 files")
        return jsonify({"error": "You can upload up to 4 files at a time."}), 400

    uploaded_files = []
    os.makedirs("uploads", exist_ok=True)
    logger.debug("Uploads directory ensured")

    for file in files:
        if file.filename == "":
            continue
        if not file.filename:
            logger.warning("Empty filename encountered in file upload")
            continue

        upload_path = os.path.join("uploads", file.filename)
        try:
            file.save(upload_path)
            logger.info(f"File saved successfully: {upload_path}")
            logger.debug(f"File size: {os.path.getsize(upload_path)} bytes")
        except Exception as e:
            logger.error(f"Error saving file {file.filename}: {e}")
        uploaded_files.append(upload_path)

    if not uploaded_files:
        logger.warning("No valid files selected for upload")
        return jsonify({"error": "No valid files selected."}), 400

    # Store uploaded file paths in the session
    session["uploaded_files"] = uploaded_files

    logger.info(
        f"Files successfully uploaded: {[os.path.basename(f) for f in uploaded_files]}"
    )
    return jsonify(
        {"success": True, "files": [os.path.basename(f) for f in uploaded_files]}
    )


@app.route("/")
@login_required
def index():
    return redirect(url_for("chat_interface"))


@app.route("/chat_interface")
@login_required
def chat_interface():
    # Get chat ID from session or create a new one
    chat_id = session.get("chat_id")
    if not chat_id:
        chat_id = generate_new_chat_id()
        session["chat_id"] = chat_id
        conversation_manager.add_message(
            chat_id,
            "user",
            "Please format your responses in Markdown."
        )

    # Get messages for the current chat
    messages = conversation_manager.get_context(chat_id)

    return render_template("chat_template.html", chat_id=chat_id, messages=messages)


@app.route("/load_chat/<chat_id>")
@login_required
def load_chat(chat_id):
    db = get_db()
    messages = db.execute(
        "SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp",
        (chat_id,),
    ).fetchall()

    return jsonify({"messages": [dict(msg) for msg in messages]})


@app.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id):
    db = get_db()
    # Verify chat belongs to current user
    chat = db.execute("SELECT user_id FROM chats WHERE id = ?", (chat_id,)).fetchone()

    if not chat or chat["user_id"] != current_user.id:
        return jsonify({"error": "Chat not found"}), 404

    # Delete messages and chat
    db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    db.commit()

    return jsonify({"success": True})


@app.route("/new_chat", methods=["POST"])
@login_required
def new_chat():
    # Generate a new chat ID and store it in the session
    chat_id = generate_new_chat_id()
    session["chat_id"] = chat_id
    conversation_manager.add_message(
        chat_id,
        "user",
        "Please format your responses in Markdown."
    )
    return jsonify({"chat_id": chat_id})


def generate_new_chat_id():
    return str(uuid.uuid4())


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    logger.debug("Received chat message")
    chat_id = session.get("chat_id")
    logger.debug(f"Chat ID: {chat_id}")
    if not chat_id:
        logger.error("Chat ID not found in session")
        return jsonify({"error": "Chat ID not found."}), 400

    data = request.get_json()
    if not data or "message" not in data:
        logger.error("Invalid request data: missing 'message' field")
        return jsonify({"error": "Message is required."}), 400

    # Get the default model configuration
    model_config = get_default_model()
    if not model_config:
        logger.error("No model configuration found")
        return jsonify({"error": "No model configuration available."}), 500
        
    # Initialize client with model configuration
    try:
        client, deployment_name = initialize_client_from_model(model_config)
    except Exception as e:
        logger.error(f"Failed to initialize client: {str(e)}")
        return jsonify({"error": str(e)}), 500

    user_message = data["message"]
    logger.info(f"Processing user message: {user_message}")
    logger.debug(f"Full message data: {data}")

    messages = conversation_manager.get_context(chat_id)
    # Escape code content by wrapping it in Markdown backticks
    if (
        "```" not in user_message
        and "def " in user_message
        or "import " in user_message
    ):
        user_message = f"```\n{user_message}\n```"
    messages.append({"role": "user", "content": user_message})

    # Analyze uploaded files
    uploaded_files = session.get("uploaded_files", [])
    file_contents = []
    for file_path in uploaded_files:
        logger.debug(f"Analyzing file: {file_path}")
        try:
            with open(file_path, "r") as file:
                file_contents.append(file.read())
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")

    # Add file contents to the context
    for content in file_contents:
        # Wrap file content in Markdown backticks to indicate it is code
        messages.append(
            {"role": "user", "content": f"File content:\n```\n{content}\n```"}
        )

    # Web scraping for weather or search queries
    if (
        "what's the weather" in user_message.lower()
        or "search for" in user_message.lower()
    ):
        logger.debug("Performing web search")
        search_result = search_web(user_message)
        logger.info(f"Search result: {search_result}")
        messages.append(
            {"role": "user", "content": f"Here's what I found:\n{search_result}"}
        )

    # Manage conversation context
    def get_relevant_context(messages, max_messages=10):
        """Get the most relevant messages for context."""
        # Always include the first message (system prompt)
        if len(messages) <= max_messages:
            return messages

        return [messages[0]] + messages[-max_messages + 1 :]

    # Generate response
    try:
        # Get relevant context
        context_messages = get_relevant_context(messages)

        # Format messages for o1-preview (all as user messages, no system messages)
        formatted_messages = [
            {"role": "user", "content": msg["content"]}
            for msg in context_messages
            if not isinstance(msg["content"], Markup)  # Exclude fallback responses
        ]

        logger.debug(f"Sending request with {len(formatted_messages)} messages")
        logger.debug(f"Using deployment: {deployment_name}")
        logger.debug(f"Payload being sent to API: {formatted_messages}")
        logger.debug(f"Exact file content included in payload: {file_contents}")
        logger.debug(f"API Endpoint: {client.base_url}")
        logger.debug(f"Model Deployment Name: {deployment_name}")
        for idx, msg in enumerate(formatted_messages):
            logger.debug(f"Message {idx}: {msg}")

        # Validate payload before sending to the API
        if not formatted_messages or not all(
            msg.get("content") for msg in formatted_messages
        ):
            raise ValueError("Invalid payload: Messages must contain content.")

        # Validate o1-preview specific requirements
        if any(msg.get("role") == "system" for msg in formatted_messages):
            logger.error("System messages are not allowed with o1-preview models")
            raise ValueError("System messages are not allowed with o1-preview models")

        if len(formatted_messages) > 10:
            logger.warning(
                "Message context length exceeds recommended limit " "for o1-preview"
            )

        # Create completion with o1-preview specific parameters
        try:
            response = client.chat.completions.create(
                model=deployment_name,  # type: ignore
                messages=[
                    {"role": "user", "content": msg["content"]}
                    for msg in formatted_messages
                ],
                temperature=1,  # Explicitly set to 1 as required by o1-preview
                max_completion_tokens=32000,  # Updated to 32000 as requested
                response_format={"type": "text"},  # Explicitly specify text format
            )
        except Exception as e:
            raise ValueError(f"Error during API call: {str(e)}")

        # Extract and validate response
        if not response.choices:
            logger.error(f"API response missing 'choices': {response}")
            logger.debug(f"Full API response: {response}")
            raise ValueError("No response choices available")

        model_response = (
            response.choices[0].message.content if response.choices[0].message else None
        )
        if not model_response:
            logger.error(f"API response contains empty content: {response}")
            logger.debug(f"Full API response structure: {response}")
            model_response = "The assistant was unable to generate a response. Please try again or rephrase your input."
            logger.info("Fallback response provided to the user.")

        # Log detailed response metrics
        logger.info("API response received successfully")
        logger.debug(f"Response content: {model_response}")
        if response.usage:
            logger.debug(
                "Token usage - Prompt: %s, Completion: %s, Total: %s",
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                response.usage.total_tokens,
            )
        logger.debug("Response finish reason: %s", response.choices[0].finish_reason)

        # Convert markdown to HTML and append copy/retry shortcuts
        model_response = Markup(markdown2.markdown(model_response))
        model_response += Markup(
            '<div class="shortcuts">'
            '<button onclick="copyToClipboard()">Copy</button>'
            '<button onclick="retryMessage()">Retry</button>'
            "</div>"
        )

        logger.info(f"Received response: {model_response}")
        logger.debug(f"Response being sent to chat interface: {model_response}")
        logger.debug(f"Raw API response: {response}")
        logger.debug(f"Usage: {response.usage}")

    except Exception as e:
        import traceback

        error_msg = str(e)
        logger.error(f"Error during API call: {error_msg}")
        logger.debug(f"API endpoint: {azure_endpoint}")
        logger.debug(f"Model deployment name: {deployment_name}")
        logger.debug(f"Traceback: {traceback.format_exc()}")

        if "rate limit" in error_msg.lower():
            model_response = (
                "The service is currently busy. Please try again in a moment."
            )
        elif "context length" in error_msg.lower():
            model_response = "The message is too long. Please try a shorter message."
        else:
            model_response = "Sorry, I encountered an error while processing your request. Please try again."

    messages.append({"role": "assistant", "content": model_response})
    # Update conversation context with all messages
    conversation_manager.clear_context(chat_id)
    for message in messages:
        conversation_manager.add_message(
            chat_id,
            message["role"],
            message["content"]
        )

    return jsonify({"response": model_response})


if __name__ == "__main__":
    app.run(debug=True)
