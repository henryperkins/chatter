from flask import Blueprint, jsonify
from sqlalchemy.inspection import inspect
from models import Chat, Model
from database import check_db_health

bp = Blueprint('debug', __name__)

@bp.route("/db-health")
def db_health():
    """Check database health and relationship mappings."""
    health_data = check_db_health()
    
    # Validate relationships
    try:
        chat_rel = inspect(Chat).relationships.get("model")
        model_rel = inspect(Model).relationships.get("chats")
        
        assert chat_rel.mapper.class_ == Model, "Chat.model relationship broken"
        assert model_rel.mapper.class_ == Chat, "Model.chats relationship broken"
        
        health_data["relationships"] = {
            "status": "healthy",
            "mappings_valid": True
        }
    except Exception as e:
        health_data["relationships"] = {
            "status": "error",
            "error": str(e),
            "mappings_valid": False
        }
    
    return jsonify(health_data)
