from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required, current_user
from conversation_manager import ConversationManager
from database import get_db
from azure_config import get_azure_client, initialize_client_from_model
from models import Chat, Model
import uuid
import logging
import os
from werkzeug.utils import secure_filename
from markupsafe import Markup
import markdown2
from azure.ai.ml import AzureOpenAI
import requests  # Import the missing module

bp = Blueprint("chat", __name__)
conversation_manager = ConversationManager()
logger = logging.getLogger(__name__)

# Initialize Azure client only once
client, deployment_name = get_azure_client()

messages = []  # Define the missing variable

@bp.route("/")
@login_required
def index():
    return redirect(url_for("chat.chat_interface"))

@bp.route("/chat_interface")
@login_required
def chat_interface():
    chat_id = session.get("chat_id")
    if not chat_id:
        chat_id = generate_new_chat_id()
        session["chat_id"] = chat_id
        conversation_manager.add_message(
            chat_id, "user", "Please format your responses in Markdown."
        )

    messages = conversation_manager.get_context(chat_id)
    context = Chat.get_context(chat_id)
    
    # Fetch models for the dropdown
    models = Model.get_all()
    
    return render_template("chat.html", chat_id=chat_id, messages=messages, context=context, models=models)

@bp.route("/load_chat/<chat_id>")
@login_required
def load_chat(chat_id):
    db = get_db()
    query = (
        "SELECT role, content, timestamp\n"
        "FROM messages\n"
        "WHERE chat_id = ?\n"
        "ORDER BY timestamp"
    )
    messages = db.execute(query, (chat_id,)).fetchall()

    context = Chat.get_context(chat_id)
    return jsonify({"messages": [dict(msg) for msg in messages], "context": context})

@bp.route("/delete_chat/<chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id):
    db = get_db()
    chat = db.execute("SELECT user_id FROM chats WHERE id = ?", (chat_id,)).fetchone()

    if not chat or chat["user_id"] != current_user.id:
        logger.warning(f"Attempt to delete non-existent or unauthorized chat: {chat_id}")
        return jsonify({"error": "Chat not found"}), 404

    db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    db.commit()

    logger.info(f"Chat {chat_id} deleted successfully")
    return jsonify({"success": True})

@bp.route("/new_chat", methods=["POST"])
@login_required
def new_chat():
    chat_id = generate_new_chat_id()
    session["chat_id"] = chat_id
    conversation_manager.add_message(
        chat_id, "user", "Please format your responses in Markdown."
    )
    logger.info(f"New chat created with ID: {chat_id}")
    return jsonify({"chat_id": chat_id})

@bp.route("/models", methods=["GET"])
@login_required
def get_models():
    """Retrieve all models."""
    models = Model.get_all()
    return jsonify([model.__dict__ for model in models])

@bp.route("/models", methods=["POST"])
@login_required
def create_model():
    """Create a new model."""
    data = request.json
    if not all(key in data for key in ['name', 'api_endpoint', 'api_key']):
        return jsonify({"error": "Missing required fields", "success": False}), 400
    try:
        model_id = Model.create(
            data['name'],
            data.get('description', ''),
            data.get('model_type', 'azure'),
            data['api_endpoint'],
            data['api_key'],
            data.get('temperature', 1.0),
            data.get('max_tokens', 32000),
            data.get('is_default', 0)
        )
        return jsonify({"id": model_id, "success": True})
    except Exception as e:
        logger.error(f"Error creating model: {e}")
        return jsonify({"error": str(e), "success": False}), 500

@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
def update_model(model_id):
    """Update an existing model."""
    data = request.json
    if not all(key in data for key in ['name', 'api_endpoint', 'api_key']):
        return jsonify({"error": "Missing required fields", "success": False}), 400
    try:
        Model.update(
            model_id,
            data['name'],
            data.get('description', ''),
            data.get('model_type', 'azure'),
            data['api_endpoint'],
            data['api_key'],
            data.get('temperature', 1.0),
            data.get('max_tokens', 32000),
            data.get('is_default', 0)
        )
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating model: {e}")
        return jsonify({"error": str(e), "success": False}), 500

@bp.route("/models/<int:model_id>", methods=["DELETE"])
@login_required
def delete_model(model_id):
    """Delete a model."""
    try:
        Model.delete(model_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting model: {e}")
        return jsonify({"error": str(e), "success": False}), 500

@bp.route("/models/default/<int:model_id>", methods=["POST"])
@login_required
def set_default_model(model_id):
    """Set a model as the default."""
    try:
        Model.set_default(model_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error setting default model: {e}")
        return jsonify({"error": str(e), "success": False}), 500

@bp.route("/scrape", methods=["POST"])
@login_required
def scrape():
    data = request.get_json()
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query is required."}), 400

    if query.startswith("what's the weather in"):
        location = query.split("what's the weather in")[1].strip()
        weather_data = scrape_weather(location)
        return jsonify({"response": weather_data})

    elif query.startswith("search for"):
        search_term = query.split("search for")[1].strip()
        search_results = scrape_search(search_term)
        return jsonify({"response": search_results})

    return jsonify({"error": "Invalid query type."}), 400

def scrape_weather(location):
    import requests
    from bs4 import BeautifulSoup

    url = f"https://www.google.com/search?q=weather+{location}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    weather = soup.find("div", class_="BNeawe").text
    return f"The weather in {location} is: {weather}"

def scrape_search(search_term):
    import requests
    from bs4 import BeautifulSoup

    url = f"https://www.google.com/search?q={search_term}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    results = soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd")
    search_results = [result.text for result in results[:3]]
    return "Search results:\n" + "\n".join(search_results)

@bp.route("/chat", methods=["POST"])
@login_required
def chat():
    logger.debug("Received chat message")
    chat_id = session.get("chat_id")
    if not chat_id:
        logger.error("Chat ID not found in session")
        return jsonify({"error": "Chat ID not found."}), 400

    data = request.get_json()
    user_message = data.get("message")

    if not user_message:
        logger.error("Invalid request data: missing 'message' field")
        return jsonify({"error": "Message is required."}), 400

    # Check for special commands
    if user_message.startswith("what's the weather in") or user_message.startswith("search for"):
        scrape_response = requests.post(
            url_for("chat.scrape", _external=True),
            json={"query": user_message},
            headers={"Authorization": f"Bearer {session.get('access_token')}"}
        )
        if scrape_response.status_code == 200:
            scrape_data = scrape_response.json()
            model_response = scrape_data["response"]
            messages = []  # Initialize messages here
            messages.append({"role": "assistant", "content": model_response})
            conversation_manager.clear_context(chat_id)
            for message in messages:
                conversation_manager.add_message(chat_id, message["role"], message["content"])
            return jsonify({"response": model_response})
        else:
            logger.error(f"Error in scraping: {scrape_response.text}")
            return jsonify({"error": "Error processing special command."}), 500

    # Apply specific formatting to the user message if it contains certain keywords
    if "```" not in user_message and ("def " in user_message or "import " in user_message):
        user_message = f"```\n{user_message}\n```"

    # Combine user message with context
    context = Chat.get_context(chat_id)
    combined_message = f"{context}\n\n{user_message}"
    messages = conversation_manager.get_context(chat_id)
    messages.append({"role": "user", "content": combined_message})

    # Load and process uploaded files, appending their contents to messages
    uploaded_files = session.get("uploaded_files", [])
    for file_path in uploaded_files:
        try:
            with open(file_path, "r") as file:
                messages.append({"role": "user", "content": f"File content:\n```\n{file.read()}\n```"})
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")

    try:
        # Retrieve the selected model or use the default
        selected_model_id = session.get("selected_model_id")
        if selected_model_id:
            model = Model.get_by_id(selected_model_id)
            if model:
                # Reinitialize the Azure client with the selected model
                client = initialize_client_from_model(model.__dict__)
            else:
                raise ValueError("Selected model not found")

        # Prepare messages for the API call
        api_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages if msg["role"] in ["user", "assistant"]]

        # Call the Azure OpenAI API to get a response
        response = client.chat.completions.create(
            model=deployment_name,
            messages=api_messages,
            temperature=1 if "o1-preview" in deployment_name else 0.7,
            max_tokens=None if "o1-preview" in deployment_name else 500,
            max_completion_tokens=500 if "o1-preview" in deployment_name else None,
            api_version="2024-12-01-preview" if "o1-preview" in deployment_name else None
        )

        # Extract and log the model's response
        model_response = response.choices[0].message.content if response.choices[0].message else "The assistant was unable to generate a response. Please try again or rephrase your input."
        logger.info(f"Response received from the model: {model_response}")

        # Update context with the latest interaction
        new_context = extract_context_from_conversation(messages, model_response)
        Chat.update_context(chat_id, new_context)

        # Add the model's response to the conversation history
        messages.append({"role": "assistant", "content": model_response})
        conversation_manager.clear_context(chat_id)
        for message in messages:
            conversation_manager.add_message(chat_id, message["role"], message["content"])

        return jsonify({"response": model_response})

    except Exception as e:
        error_message = f"Unexpected Error: {str(e)}"
        logger.error(error_message)
        return jsonify({"error": error_message}), 500

@bp.route("/chat/<chat_id>/context", methods=["POST"])
@login_required
def update_context(chat_id):
    data = request.get_json()
    context = data.get("context", "")
    Chat.update_context(chat_id, context)
    logger.info(f"Context updated for chat ID: {chat_id}")
    return jsonify({"success": True})

@bp.route('/upload', methods=['POST'])
@login_required
def upload_files():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'})

    files = request.files.getlist('file')
    if not files:
        return jsonify({'success': False, 'error': 'No files selected'})

    uploaded_files = []
    for file in files:
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'})
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join('uploads', current_user.username, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            uploaded_files.append(file_path)

    # Store the uploaded file paths in the session
    session['uploaded_files'] = uploaded_files

    return jsonify({'success': True, 'files': [secure_filename(file.filename) for file in files]})

def generate_new_chat_id():
    return str(uuid.uuid4())

def extract_context_from_conversation(messages, latest_response):
    """Extract key context from the conversation"""
    context_parts = []
    for msg in messages[-10:]:  # Consider last 10 messages for context
        if msg["role"] in ["assistant", "user"]:
            context_parts.append(f"{msg['role']}: {msg['content']}")
    
    context_parts.append(f"assistant: {latest_response}")
    
    context = "\n".join(context_parts)
    return context[:4000]  # Limit context to 4000 characters
