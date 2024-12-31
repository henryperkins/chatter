from models import Chat
import uuid

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
