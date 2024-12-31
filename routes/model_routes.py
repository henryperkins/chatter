# routes/model_routes.py

from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required
from models import Model
from decorators import admin_required
import logging

bp = Blueprint('model', __name__)
logger = logging.getLogger(__name__)


@bp.route("/models", methods=["GET"])
@login_required
def get_models():
    """Retrieve all models with pagination."""
    try:
        limit = request.args.get("limit", 10, type=int)
        offset = request.args.get("offset", 0, type=int)
        models = Model.get_all(limit, offset)
        return jsonify(
            [
                {
                    "id": model.id,
                    "name": model.name,
                    "description": model.description,
                    "is_default": model.is_default,
                }
                for model in models
            ]
        )
    except Exception as e:
        logger.error(f"Error retrieving models: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route('/models', methods=['POST'])
@login_required
@admin_required
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
@admin_required
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
@admin_required
def delete_model(model_id):
    """Delete a model."""
    Model.delete(model_id)
    return jsonify({"success": True})

@bp.route("/add-model", methods=["GET"])
@login_required
def add_model_page():
    """Render the add model page."""
    return render_template("add_model.html")

@bp.route('/models/default/<int:model_id>', methods=['POST'])
@login_required
def set_default_model(model_id):
    """Set a model as the default."""
    Model.set_default(model_id)
    return jsonify({"success": True})
