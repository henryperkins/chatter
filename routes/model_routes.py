# routes/model_routes.py

from flask import Blueprint, jsonify, request
from flask_login import login_required
from models import Model
import logging

bp = Blueprint('model', __name__)
logger = logging.getLogger(__name__)

@bp.route('/models', methods=['GET'])
@login_required
def get_models():
    """Retrieve all models."""
    models = Model.get_all()
    return jsonify([model.__dict__ for model in models])

@bp.route('/models', methods=['POST'])
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

@bp.route('/models/<int:model_id>', methods=['PUT'])
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

@bp.route('/models/<int:model_id>', methods=['DELETE'])
@login_required
def delete_model(model_id):
    """Delete a model."""
    Model.delete(model_id)
    return jsonify({"success": True})

@bp.route('/models/default/<int:model_id>', methods=['POST'])
@login_required
def set_default_model(model_id):
    """Set a model as the default."""
    Model.set_default(model_id)
    return jsonify({"success": True})
