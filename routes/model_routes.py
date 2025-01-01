"""
model_routes.py

This module defines the routes for managing AI models, including
creating, updating, deleting, and retrieving models.
"""

from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from models import Model
from decorators import admin_required
import logging

bp = Blueprint("model", __name__)
logger = logging.getLogger(__name__)


@bp.route("/models", methods=["GET"])
@login_required
def get_models():
    """Retrieve all models with optional pagination."""
    try:
        limit = request.args.get("limit", 10, type=int)
        offset = request.args.get("offset", 0, type=int)
        models = Model.get_all(limit, offset)
        return jsonify(
            [
                {
                    "id": model.id,
                    "name": model.name,
                    "deployment_name": model.deployment_name,
                    "description": model.description,
                    "is_default": model.is_default,
                    "requires_o1_handling": model.requires_o1_handling,
                    "api_version": model.api_version,
                }
                for model in models
            ]
        )
    except Exception as e:
        logger.error("Error retrieving models: %s", str(e))
        return jsonify({"error": "An error occurred while retrieving models"}), 500


@bp.route("/models", methods=["POST"])
@login_required
@admin_required
def create_model():
    """Create a new model."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request data", "success": False}), 400

    try:
        Model.validate_model_config(data)
        model_id = Model.create(
            name=data["name"],
            deployment_name=data["deployment_name"],
            description=data.get("description", ""),
            model_type=data.get("model_type", "azure"),
            api_endpoint=data["api_endpoint"],
            temperature=float(data.get("temperature", 1.0)),
            max_tokens=int(data.get("max_tokens")) if data.get("max_tokens") else None,
            max_completion_tokens=int(data.get("max_completion_tokens", 500)),
            is_default=bool(data.get("is_default", 0)),
            requires_o1_handling=bool(data.get("requires_o1_handling", 0)),
            api_version=data.get("api_version", "2024-10-01-preview"),
        )
        logger.info("Model created successfully: %s", data["name"])
        return jsonify({"id": model_id, "success": True})
    except ValueError as e:
        logger.error("Error creating model: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 400
    except KeyError as e:
        missing_field = e.args[0]
        logger.error("Missing required field: %s", missing_field)
        return (
            jsonify(
                {"error": f"Missing required field: {missing_field}", "success": False}
            ),
            400,
        )
    except Exception as e:
        logger.error("Unexpected error: %s", str(e))
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500


@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def update_model(model_id: int):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided", "success": False}), 400

        Model.validate_model_config(data)
        Model.update(model_id=model_id, **data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


@bp.route("/models/<int:model_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_model(model_id: int):
    try:
        Model.delete(model_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


@bp.route("/add-model", methods=["GET"])
@login_required
@admin_required
def add_model_page():
    """Render the add model page."""
    return render_template("add_model.html")


@bp.route("/models/default/<int:model_id>", methods=["POST"])
@login_required
@admin_required
def set_default_model(model_id: int):
    """Set a model as the default."""
    Model.set_default(model_id)
    return jsonify({"success": True})
