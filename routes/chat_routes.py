from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from flask_login import login_required, current_user
from conversation_manager import ConversationManager
from database import get_db
from models import Chat, Model
import logging
from flask import render_template
from chat_api import get_azure_response, scrape_data
from chat_utils import generate_new_chat_id, extract_context_from_conversation
from werkzeug.utils import secure_filename
import os

bp = Blueprint("chat", __name__)
conversation_manager = ConversationManager()
logger = logging.getLogger(__name__)

@bp.route("/new-chat", methods=["GET"])
@login_required
def new_chat_page():
    """Render the new chat page."""
    return render_template("new_chat.html")

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
    # Verify chat ownership
    chat = db.execute(
        "SELECT id FROM chats WHERE id = ? AND user_id = ?",
        (chat_id, current_user.id),
    ).fetchone()

    if not chat:
        logger.warning(f"Unauthorized access attempt to chat {chat_id}")
        return jsonify({"error": "Chat not found or access denied"}), 403

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

    if not chat or int(chat["user_id"]) != int(current_user.id):
        logger.warning(f"Attempt to delete non-existent or unauthorized chat: {chat_id}")
        return jsonify({"error": "Chat not found or access denied"}), 403

    db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    db.commit()

    logger.info(f"Chat {chat_id} deleted successfully")
    return jsonify({"success": True})

@bp.route("/new_chat", methods=["GET"])
@login_required
def new_chat_route():
    """Create a new chat and redirect to the chat interface."""
    chat_id = generate_new_chat_id()
    # Ensure current_user.id is an integer
    user_id = int(current_user.id)
    # Create a new chat in the database
    Chat.create(chat_id, user_id, "New Chat")
    session["chat_id"] = chat_id
    # Add the default message to the conversation
    conversation_manager.add_message(
        chat_id, "user", "Please format your responses in Markdown."
    )
    logger.info(f"New chat created with ID: {chat_id}")
    return redirect(url_for("chat.chat_interface"))

@bp.route("/conversations", methods=["GET"])
@login_required
def get_conversations():
    """Retrieve all conversations for the current user."""
    user_id = int(current_user.id)
    conversations = Chat.get_user_chats(user_id)
    return jsonify(conversations)

@bp.route("/scrape", methods=["POST"])
@login_required
def scrape():
    data = request.get_json()
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query is required."}), 400

    try:
        response = scrape_data(query)
        return jsonify({"response": response})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

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
        try:
            model_response = scrape_data(user_message)
            messages = [{"role": "assistant", "content": model_response}]
            conversation_manager.clear_context(chat_id)
            for message in messages:
                conversation_manager.add_message(chat_id, message["role"], message["content"])
            return jsonify({"response": model_response})
        except ValueError as e:
            logger.error(f"Error in scraping: {str(e)}")
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
        # Assuming deployment_name is defined elsewhere or passed as a parameter
        deployment_name = "default_deployment_name"  # This should be replaced with actual logic to get deployment_name
        model_response = get_azure_response(messages, deployment_name, selected_model_id)

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
    # Verify chat ownership
    chat = Chat.get_by_id(chat_id)
    if not chat or chat.user_id != current_user.id:
        logger.warning(f"Unauthorized context update attempt for chat {chat_id}")
        return jsonify({"error": "Chat not found or access denied"}), 403

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
