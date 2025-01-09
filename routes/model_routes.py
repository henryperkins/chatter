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
)
from flask_login import login_required
from models import Model
from decorators import admin_required
from forms import ModelForm
from extensions import csrf

bp = Blueprint("model", __name__)
logger = logging.getLogger(__name__)


@bp.route("/models", methods=["GET"])
@login_required
def get_models():
    """
    Retrieve all models with optional pagination.
    """
    try:
        limit = request.args.get("limit", 10, type=int)
        offset = request.args.get("offset", 0, type=int)
        models = Model.get_all(limit, offset)

        model_list = [
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
            for m in models
        ]
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

        logger.debug(
            "Creating model with data: %s",
            {k: v for k, v in data.items() if k != "api_key"},
        )

        Model.validate_model_config(data)

        model_id = Model.create(data)
        return jsonify(
            {
                "id": model_id,
                "success": True,
                "message": "Model created successfully",
            }
        )

    except ValueError as e:
        logger.error("Validation error: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 400
    except Exception as e:
        logger.exception("Error creating model")
        if "UNIQUE constraint failed: models.deployment_name" in str(e):
            return (
                jsonify(
                    {
                        "error": "A model with this deployment name already exists",
                        "success": False,
                    }
                ),
                400,
            )
        return (
            jsonify({"error": "An unexpected error occurred", "success": False}),
            500,
        )


@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def update_model(model_id: int):
    """
    Update an existing model (admin-only).
    """
    # Verify CSRF token for AJAX requests
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        csrf_token = request.headers.get("X-CSRFToken")
        if not csrf_token or not csrf.validate_csrf(csrf_token):
            return (
                jsonify({"success": False, "error": "CSRF token invalid or missing"}),
                400,
            )

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
        logger.exception("Unexpected error during model update: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 500


@bp.route("/models/<int:model_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_model(model_id: int):
    """
    Delete a model (admin-only).
    """
    # Verify CSRF token for AJAX requests
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        csrf_token = request.headers.get("X-CSRFToken")
        if not csrf_token or not csrf.validate_csrf(csrf_token):
            return (
                jsonify({"success": False, "error": "CSRF token invalid or missing"}),
                400,
            )

    try:
        Model.delete(model_id)
        return jsonify({"success": True})
    except ValueError as e:
        error_msg = str(e)
        logger.error("Attempted to delete a model in use: %s", error_msg)
        return jsonify({"error": error_msg, "success": False}), 400
    except Exception as e:
        error_msg = str(e)
        logger.exception("Unexpected error during model deletion: %s", error_msg)
        return jsonify({"error": error_msg, "success": False}), 500


@bp.route("/add-model", methods=["GET"])
@login_required
@admin_required
def add_model_page():
    """
    Render a page for adding a model.
    """
    form = ModelForm()
    return render_template("add_model.html", form=form)


@bp.route("/edit/<int:model_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_model(model_id):
    """
    Render the edit model page (GET) and handle form submission (POST).
    """
    model = Model.get_by_id(model_id)
    if not model:
        flash("Model not found", "error")
        return redirect(url_for("chat.chat_interface"))

    form = ModelForm(obj=model)

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                existing_model = Model.get_by_id(model_id)
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
                    "api_key": existing_model.api_key,  # Preserve existing API key
                }
                logger.debug(
                    "Updating model %d with data: %s",
                    model_id,
                    {k: v for k, v in data.items() if k != "api_key"},
                )
                Model.update(model_id, data)

                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify(
                        {"success": True, "message": "Model updated successfully"}
                    )
                else:
                    flash("Model updated successfully", "success")
                    return redirect(url_for("chat.chat_interface"))

            except Exception as e:
                logger.exception("Error updating model %d: %s", model_id, str(e))
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"error": str(e), "success": False}), 400
                else:
                    flash(f"Error updating model: {str(e)}", "error")
                    return render_template("edit_model.html", form=form, model=model)
        else:
            logger.error("Form validation failed: %s", form.errors)
            return jsonify({"error": form.errors, "success": False}), 400

    return render_template("edit_model.html", form=form, model=model)


@bp.route("/models/default/<int:model_id>", methods=["POST"])
@login_required
@admin_required
def set_default_model(model_id: int):
    """
    Set a model as the default (admin-only).
    """
    # Verify CSRF token for AJAX requests
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        csrf_token = request.headers.get("X-CSRFToken")
        if not csrf_token or not csrf.validate_csrf(csrf_token):
            return (
                jsonify({"success": False, "error": "CSRF token invalid or missing"}),
                400,
            )

    try:
        Model.set_default(model_id)
        return jsonify({"success": True})
    except Exception:
        logger.exception("Unexpected error setting default model")
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500


@bp.route("/models/<int:model_id>/immutable-fields", methods=["GET"])
@login_required
def get_immutable_fields(model_id: int):
    """
    Retrieve any immutable fields for the specified model.
    """
    try:
        immutable_fields = Model.get_immutable_fields(model_id)
        return jsonify(immutable_fields)
    except Exception as e:
        logger.error("Error retrieving immutable fields: %s", str(e))
        return (
            jsonify({"error": f"Error retrieving immutable fields: {str(e)}"}),
            500,
        )


@bp.route("/models/<int:model_id>/versions", methods=["GET"])
@login_required
def get_version_history(model_id: int):
    """
    Retrieve version history for a model.
    """
    try:
        versions = Model.get_version_history(model_id)
        return jsonify(versions)
    except Exception as e:
        error_msg = str(e)
        logger.error("Error retrieving version history: %s", error_msg)
        return (
            jsonify({"error": error_msg}),
            500,
        )


@bp.route("/models/<int:model_id>/revert/<int:version>", methods=["POST"])
@login_required
@admin_required
def revert_to_version(model_id: int, version: int):
    """
    Revert a model to a previous version (admin-only).
    """
    # Verify CSRF token for AJAX requests
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        csrf_token = request.headers.get("X-CSRFToken")
        if not csrf_token or not csrf.validate_csrf(csrf_token):
            return (
                jsonify({"success": False, "error": "CSRF token invalid or missing"}),
                400,
            )
    try:
        Model.revert_to_version(model_id, version)
        return jsonify({"success": True})
    except ValueError as e:
        logger.error("Error reverting model: %s", str(e))
        return jsonify({"error": str(e), "success": False}), 400
    except Exception as e:
        error_msg = str(e)
        logger.exception("Unexpected error during model revert: %s", error_msg)
        return jsonify({"error": error_msg, "success": False}), 500
