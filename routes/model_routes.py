"""
model_routes.py

This module defines the routes for managing AI models, including
creating, updating, deleting, and retrieving models.
"""

import logging
from flask import (
    Blueprint,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import login_required, current_user
from database import get_db  # Use the centralized context manager
from models import Model
from decorators import admin_required
from forms import ModelForm

bp = Blueprint("model", __name__)
logger = logging.getLogger(__name__)


@bp.route("/models", methods=["GET"])
@login_required
def get_models():
    """
    Retrieve all models with optional pagination.

    This route handles a GET request that returns a paginated list of
    models. You can supply `limit` and `offset` as query parameters to
    paginate the results. Example: /models?limit=10&offset=20

    Returns:
        JSON response containing an array of model data.
    """
    try:
        limit = request.args.get("limit", 10, type=int)
        offset = request.args.get("offset", 0, type=int)
        models = Model.get_all(limit, offset)

        # Convert model objects to dictionaries for JSON serialization
        model_list = []
        for m in models:
            model_list.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "deployment_name": m.deployment_name,
                    "description": m.description,
                    "is_default": m.is_default,
                    "requires_o1_handling": m.requires_o1_handling,
                    "api_version": m.api_version,
                    "version": m.version,
                }
            )
        return jsonify(model_list)

    except Exception as e:
        logger.error("Error retrieving models: %s", str(e))
        return jsonify({"error": "An error occurred while retrieving models"}), 500


@bp.route("/models", methods=["POST"])
@login_required
@admin_required
def create_model():
    """
    Create a new model (admin-only).

    Expects form data corresponding to ModelForm fields:
    - name, deployment_name, description, api_endpoint, temperature,
      max_tokens, max_completion_tokens, model_type, api_version,
      requires_o1_handling, is_default
    """
    form = ModelForm()
    if not form.validate_on_submit():
        logger.error("Form validation failed: %s", form.errors)
        return jsonify({"error": form.errors, "success": False}), 400

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
            "is_default": form.is_default.data,
        }

        # Log model creation attempt without sensitive data
        logger.debug("Creating model with data: %s", {
            k: v for k, v in data.items() if k != 'api_key'
        })

        # Validate the data before creating the model
        Model.validate_model_config(data)

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
        if "UNIQUE constraint failed: models.deployment_name" in str(e):
            return jsonify({
                "error": "A model with this deployment name already exists",
                "success": False
            }), 400
        return jsonify({
            "error": "An unexpected error occurred",
            "success": False
        }), 500


@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def update_model(model_id: int):
    """
    Update an existing model (admin-only).

    JSON body structure might look like:
    {
        "name": "...",
        "deployment_name": "...",
        "description": "...",
        "api_endpoint": "...",
        "temperature": 0.7,
        "max_tokens": 2048,
        "max_completion_tokens": 500,
        "model_type": "GPT-3.5",
        "api_version": "2023-XX-XX",
        "requires_o1_handling": false,
        "is_default": false
    }
    """
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
    """
    Delete a model (admin-only).

    This operation should be approached carefully if the model is in use.
    """
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
    """
    Render a page (if you have a template) for adding a model.
    The form includes fields like name, deployment_name, etc.
    """
    form = ModelForm()
    return render_template("add_model.html", form=form)


@bp.route("/edit-model/<int:model_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_model_page(model_id):
    """
    Render the edit model page (GET) and handle form submission (POST).
    If model is not found, redirect to a relevant page.
    """
    model = Model.get_by_id(model_id)
    if not model:
        flash("Model not found", "error")
        return redirect(url_for("chat.chat_interface"))

    form = ModelForm(obj=model)

    if form.validate_on_submit():
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
            "is_default": form.is_default.data,
        }
        Model.update(model_id, data)
        flash("Model updated successfully", "success")
        return redirect(url_for("chat.chat_interface"))

    return render_template("edit_model.html", form=form, model=model)


@bp.route("/models/default/<int:model_id>", methods=["POST"])
@login_required
@admin_required
def set_default_model(model_id: int):
    """
    Set a model as the default (admin-only).

    Only one model should be default at a time, so this route likely
    unsets the default flag on other models and sets it on this one.
    """
    try:
        Model.set_default(model_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Unexpected error setting default model")
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500


@bp.route("/models/<int:model_id>/immutable-fields", methods=["GET"])
@login_required
def get_immutable_fields(model_id: int):
    """
    Retrieve any immutable fields for the specified model. Typically
    used to prevent certain fields from being changed via the UI
    or certain routes.
    """
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
    """
    Retrieve version history for a model (if you store historical
    snapshots or maintain a versioning system).
    """
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
    """
    Revert a model to a previous version (admin-only).
    Expects that `Model.revert_to_version` handles any validation
    or database logic to restore that version.
    """
    try:
        Model.revert_to_version(model_id, version)
        return jsonify({"success": True})
    except ValueError as e:
        logger.error("Error reverting model: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 400
    except Exception as e:
        logger.exception("Unexpected error during model revert")
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500
