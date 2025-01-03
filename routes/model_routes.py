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
from forms import ModelForm

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
                    "version": model.version,
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
    form = ModelForm()
    if form.validate_on_submit():
        try:
            data = {
                "name": form.name.data,
                "deployment_name": form.deployment_name.data,
                "description": form.description.data,
                "api_endpoint": form.api_endpoint.data,
                "temperature": form.temperature.data,
                "max_tokens": form.max_tokens.data,
                "max_completion_tokens": form.max_completion_tokens.data,
                "model_type": form.model_type.data,
                "api_version": form.api_version.data,
                "requires_o1_handling": form.requires_o1_handling.data,
                "is_default": form.is_default.data
            }
            model_id = Model.create(data)
            return jsonify({
                "id": model_id,
                "success": True,
                "message": "Model created successfully"
            })
        except ValueError as e:
            logger.error("Validation error: %s", str(e))
            return jsonify({"error": str(e), "success": False}), 400
        except Exception as e:
            logger.exception("Error creating model")
            return jsonify({"error": "An unexpected error occurred", "success": False}), 500

    return jsonify({"error": form.errors, "success": False}), 400


@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def update_model(model_id: int):
    """Update an existing model."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided", "success": False}), 400

    try:
        Model.update(model_id, data)
        return jsonify({"success": True})
    except ValueError as e:
        logger.error("Validation error during model update: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 400
    except Exception as e:
        logger.exception("Unexpected error during model update")
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500


@bp.route("/models/<int:model_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_model(model_id: int):
    """Delete a model."""
    try:
        Model.delete(model_id)
        return jsonify({"success": True})
    except ValueError as e:
        logger.error("Attempted to delete a model in use: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 400
    except Exception as e:
        logger.exception("Unexpected error during model deletion")
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500


@bp.route("/add-model", methods=["GET"])
@login_required
@admin_required
def add_model_page():
    """Render the add model page."""
    form = ModelForm()
    return render_template("add_model.html", form=form)


@bp.route("/models/default/<int:model_id>", methods=["POST"])
@login_required
@admin_required
def set_default_model(model_id: int):
    """Set a model as the default."""
    try:
        Model.set_default(model_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Unexpected error setting default model")
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500


@bp.route("/models/<int:model_id>/immutable-fields", methods=["GET"])
@login_required
def get_immutable_fields(model_id: int):
    """Retrieve immutable fields for a model."""
    try:
        immutable_fields = Model.get_immutable_fields(model_id)
        return jsonify(immutable_fields)
    except Exception as e:
        logger.error("Error retrieving immutable fields: %s", str(e))
        return (
            jsonify({"error": "An error occurred while retrieving immutable fields"}),
            500,
        )


@bp.route("/models/<int:model_id>/versions", methods=["GET"])
@login_required
def get_version_history(model_id: int):
    """Retrieve version history for a model."""
    try:
        versions = Model.get_version_history(model_id)
        return jsonify(versions)
    except Exception as e:
        logger.error("Error retrieving version history: %s", str(e))
        return (
            jsonify({"error": "An error occurred while retrieving version history"}),
            500,
        )


@bp.route("/models/<int:model_id>/revert/<int:version>", methods=["POST"])
@login_required
@admin_required
def revert_to_version(model_id: int, version: int):
    """Revert a model to a previous version."""
    try:
        Model.revert_to_version(model_id, version)
        return jsonify({"success": True})
    except ValueError as e:
        logger.error("Error reverting model: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 400
    except Exception as e:
        logger.exception("Unexpected error during model revert")
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500
