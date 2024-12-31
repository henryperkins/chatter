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
    """Retrieve all models with pagination."""
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)
    models = Model.get_all(limit, offset)
    return jsonify([model.__dict__ for model in models])

@bp.route('/models', methods=['POST'])
@login_required
def create_model():
    """Create a new model."""
    data = request.json
    try:
        Model.validate_model_config(data)
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
        logger.info(f"Model created successfully: {data['name']}")
        return jsonify({"id": model_id, "success": True})
    except ValueError as e:
        logger.error(f"Error creating model: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 400

@bp.route('/models/<int:model_id>', methods=['PUT'])
@login_required
def update_model(model_id):
    """Update an existing model."""
    data = request.json
    try:
        Model.validate_model_config(data)
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
        logger.info(f"Model updated successfully: {data['name']}")
        return jsonify({"success": True})
    except ValueError as e:
        logger.error(f"Error updating model: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 400

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
