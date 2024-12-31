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
from markupsafe import Markup
import markdown2
from azure.ai.ml import AzureOpenAI

bp = Blueprint("chat", __name__)
conversation_manager = ConversationManager()
logger = logging.getLogger(__name__)

# Initialize Azure client
client, deployment_name = get_azure_client()


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
    return render_template("chat.html", chat_id=chat_id, messages=messages, context=context)


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


@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
def update_model(model_id):
    """Update an existing model."""
    data = request.json
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


@bp.route("/models/<int:model_id>", methods=["DELETE"])
@login_required
def delete_model(model_id):
    """Delete a model."""
    Model.delete(model_id)
    return jsonify({"success": True})


@bp.route("/models/default/<int:model_id>", methods=["POST"])
@login_required
def set_default_model(model_id):
    """Set a model as the default."""
    Model.set_default(model_id)
    return jsonify({"success": True})


@bp.route("/chat", methods=["POST"])
@login_required
def chat():
    logger.debug("Received chat message")
    chat_id = session.get("chat_id")
    if not chat_id:
        logger.error("Chat ID not found in session")
        return jsonify({"error": "Chat ID not found."}), 400

    data = request.get_json()
    if not data or "message" not in data:
        logger.error("Invalid request data: missing 'message' field")
        return jsonify({"error": "Message is required."}), 400

    user_message = data["message"]
    messages = conversation_manager.get_context(chat_id)
    context = Chat.get_context(chat_id)

    if "```" not in user_message and (
        "def " in user_message or "import " in user_message
    ):
        user_message = f"```\n{user_message}\n```"

    combined_message = f"{context}\n\n{user_message}"
    messages.append({"role": "user", "content": combined_message})

    uploaded_files = session.get("uploaded_files", [])
    file_contents = []
    for file_path in uploaded_files:
        try:
            with open(file_path, "r") as file:
                file_contents.append(file.read())
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")

    for content in file_contents:
        messages.append(
            {"role": "user", "content": f"File content:\n```\n{content}\n```"}
        )

    try:
        if not deployment_name:
            raise ValueError("Azure deployment name is not configured")

        # Use the selected model from the session
        selected_model_id = session.get("selected_model_id")
        if selected_model_id:
            model = Model.get_by_id(selected_model_id)
            if model:
                deployment_name = model.name
                client = initialize_client_from_model(model.__dict__)
            else:
                raise ValueError("Selected model not found")

        api_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        
        response = client.chat.completions.create(
            model=deployment_name,
            messages=api_messages,
            temperature=1,
            max_tokens=500
        )

        model_response = (
            response.choices[0].message.content
            if response.choices[0].message
            else "The assistant was unable to generate a response. Please try again or rephrase your input."
        )

        new_context = extract_context_from_conversation(messages, model_response)
        Chat.update_context(chat_id, new_context)

        model_response = model_response

    except Exception as e:
        error_message = f"Unexpected Error: {str(e)}"
        logger.error(error_message)
        model_response = error_message

    messages.append({"role": "assistant", "content": model_response})
    conversation_manager.clear_context(chat_id)
    for message in messages:
        conversation_manager.add_message(chat_id, message["role"], message["content"])

    logger.info(f"Chat response sent for chat ID: {chat_id}")
    return jsonify({"response": model_response})


@bp.route("/chat/<chat_id>/context", methods=["POST"])
@login_required
def update_context(chat_id):
    data = request.get_json()
    context = data.get("context", "")
    Chat.update_context(chat_id, context)
    logger.info(f"Context updated for chat ID: {chat_id}")
    return jsonify({"success": True})


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
