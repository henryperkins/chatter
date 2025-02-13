"""
Chat module initialization.
Exposes main chat functionality and blueprints.
"""

from flask import Blueprint

# Import core components
from .chat_core import chat_routes
from .chat_messaging import handle_chat, stream_response, handle_chat_stream
from .chat_statistics import (
    generate_usage_report,
    track_token_usage,
    get_chat_metrics,
    get_chat_stats,
    log_client_event,
    log_client_error
)
from .chat_session import (
    new_chat,
    delete_chat,
    update_chat_title,
    update_model,
    get_chat_context,
    get_user_chats
)

# Register routes with blueprint
chat_routes.add_url_rule('/send', 'handle_chat', handle_chat, methods=['POST'])
chat_routes.add_url_rule('/send_stream', 'handle_chat_stream', handle_chat_stream, methods=['POST'])
chat_routes.add_url_rule('/stats/<chat_id>', 'get_chat_stats', get_chat_stats)
chat_routes.add_url_rule('/api/log', 'log_client_event', log_client_event, methods=['POST'])
chat_routes.add_url_rule('/api/log/error', 'log_client_error', log_client_error, methods=['POST'])
chat_routes.add_url_rule('/new', 'new_chat', new_chat, methods=['POST'])
chat_routes.add_url_rule('/delete_chat/<chat_id>', 'delete_chat', delete_chat, methods=['DELETE'])
chat_routes.add_url_rule('/update_chat_title/<chat_id>', 'update_chat_title', update_chat_title, methods=['POST'])
chat_routes.add_url_rule('/update_model', 'update_model', update_model, methods=['POST'])
chat_routes.add_url_rule('/get_chat_context/<chat_id>', 'get_chat_context', get_chat_context)
chat_routes.add_url_rule('/user_chats', 'get_user_chats', get_user_chats)

# Version info
__version__ = '1.0.0'

# Expose main blueprint
__all__ = ['chat_routes']