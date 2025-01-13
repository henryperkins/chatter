import logging
from typing import Optional

from flask import (
    Blueprint,
    jsonify,
    request,
    render_template,
)
from flask_login import login_required
from flask_wtf.csrf import validate_csrf as flask_validate_csrf
from werkzeug.exceptions import HTTPException

from decorators import admin_required
from forms import ModelForm
from models import Model

bp = Blueprint("model", __name__)
logger = logging.getLogger(__name__)

def validate_csrf_token() -> Optional[tuple]:
    """Validate CSRF token for all POST, PUT, and DELETE requests."""
    try:
        csrf_token = request.headers.get("X-CSRFToken")
        if not csrf_token:
            raise ValueError("CSRF token missing.")
        flask_validate_csrf(csrf_token)
        return None
    except Exception as e:
        return jsonify({"success": False, "error": "CSRF token invalid"}), 400

def handle_error(error: Exception, message: str, status_code: int = 500) -> tuple:
    """Handle errors with proper logging and responses."""
    if isinstance(error, ValueError):
        status_code = 400
    elif isinstance(error, HTTPException):
        status_code = error.code

    logger.error(f"{message}: {str(error)}")
    return jsonify({"error": str(error), "success": False}), status_code

def extract_model_data(form: ModelForm) -> dict:
    """
    Extract model data from a form.

    Args:
        form: The ModelForm instance containing form data

    Returns:
        dict: Dictionary containing model configuration data
    """
    return {
        "name": form.name.data,
        "deployment_name": form.deployment_name.data,
        "description": form.description.data,
        "api_endpoint": form.api_endpoint.data,
        "api_key": form.api_key.data,
        "temperature": form.temperature.data,
        "max_tokens": form.max_tokens.data,
        "max_completion_tokens": form.max_completion_tokens.data,
        "model_type": form.model_type.data,
        "api_version": form.api_version.data,
        "requires_o1_handling": form.requires_o1_handling.data,
        "supports_streaming": form.supports_streaming.data,
        "is_default": form.is_default.data,
        "version": form.version.data,
    }


def validate_immutable_fields(model_id: int, data: dict) -> None:
    """
    Validate that immutable fields are not being updated.
    """
    immutable_fields = Model.get_immutable_fields(model_id)
    for field in immutable_fields:
        if field in data:
            raise ValueError(f"{field} is immutable and cannot be updated")


# Routes
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
        return handle_error(e, "Error retrieving models")

@bp.route("/models", methods=["POST"])
@login_required
@admin_required
def create_model():
    """
    Create a new model (admin-only).
    """
    csrf_error = validate_csrf_token()
    if csrf_error:
        return csrf_error

    form = ModelForm()
    if not form.validate_on_submit():
        logger.error("Form validation failed: %s", form.errors)
        return jsonify({"error": form.errors, "success": False}), 400

    try:
        data = extract_model_data(form)
        
        # Validate required fields
        required_fields = ["name", "deployment_name", "api_endpoint", "api_key"]
        for field in required_fields:
            if not data.get(field):
                raise ValueError(f"Missing required field: {field}")

        # Validate API endpoint
        if not data["api_endpoint"].startswith("https://"):
            raise ValueError("API endpoint must be a valid HTTPS URL.")

        logger.info(
            "Creating model with data: %s",
            {k: v if k != "api_key" else "****" for k, v in data.items()},
        )
        Model.validate_model_config(data)
        model_id = Model.create(data)
        logger.info(f"Model created successfully with ID: {model_id}")
        return jsonify(
            {"id": model_id, "success": True, "message": "Model created successfully"}
        ), 201

    except ValueError as e:
        return handle_error(e, "Validation error during model creation", 400)
    except Exception as e:
        if "UNIQUE constraint failed: models.deployment_name" in str(e):
            return handle_error(e, "A model with this deployment name already exists", 400)
        return handle_error(e, "Unexpected error during model creation")


@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def update_model(model_id: int):
    """
    Update an existing model (admin-only).
    """
    csrf_error = validate_csrf_token()
    if csrf_error:
        return csrf_error

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided", "success": False}), 400

    try:
        logger.info(f"Updating model with ID: {model_id}")
        validate_immutable_fields(model_id, data)
        Model.update(model_id, data)
        logger.info(f"Model updated successfully: {model_id}")
        return jsonify({"success": True, "message": "Model updated successfully"})

    except ValueError as e:
        return handle_error(e, "Validation error during model update", 400)
    except Exception as e:
        return handle_error(e, "Unexpected error during model update")


@bp.route("/models/<int:model_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_model(model_id: int):
    """
    Delete a model (admin-only).
    """
    csrf_error = validate_csrf_token()
    if csrf_error:
        return csrf_error

    try:
        logger.info(f"Deleting model with ID: {model_id}")
        Model.delete(model_id)
        logger.info(f"Model deleted successfully: {model_id}")
        return jsonify({"success": True, "message": "Model deleted successfully"})

    except ValueError as e:
        return handle_error(e, f"Error deleting model {model_id}", 400)
    except Exception as e:
        return handle_error(e, f"Unexpected error during model deletion {model_id}")

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
    """Edit model route handler."""
    try:
        model = Model.get_by_id(model_id)
        if not model:
            return jsonify({"error": "Model not found"}), 404

        form = ModelForm(obj=model)

        if request.method == "POST":
            csrf_error = validate_csrf_token()
            if csrf_error:
                return csrf_error

            if form.validate_on_submit():
                try:
                    data = extract_model_data(form)
                    validate_immutable_fields(model_id, data)
                    Model.update(model_id, data)
                    logger.info(f"Model updated successfully: {model_id}")
                    return jsonify({"success": True, "message": "Model updated successfully"})
                except Exception as e:
                    return handle_error(e, "Error updating model", 400)

            return jsonify({"error": form.errors}), 400

        return render_template("edit_model.html", form=form, model=model)

    except Exception as e:
        return handle_error(e, "Error in edit_model")

@bp.route("/models/default/<int:model_id>", methods=["POST"])
@login_required
@admin_required
def set_default_model(model_id: int):
    """
    Set a model as the default (admin-only).
    """
    csrf_error = validate_csrf_token()
    if csrf_error:
        return csrf_error

    try:
        logger.info(f"Setting model {model_id} as default")
        Model.set_default(model_id)
        logger.info(f"Model {model_id} set as default successfully")
        return jsonify(
            {"success": True, "message": "Model set as default successfully"}
        )
    except Exception as e:
        return handle_error(e, "Unexpected error setting default model")

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
        return handle_error(e, "Error retrieving immutable fields")

@bp.route("/models/<int:model_id>/versions", methods=["GET"])
@login_required
def get_version_history(model_id: int):
    """
    Retrieve version history for a model.
    """
    try:
        limit = request.args.get("limit", 10, type=int)
        offset = request.args.get("offset", 0, type=int)
        versions = Model.get_version_history(model_id, limit, offset)
        return jsonify(versions)
    except Exception as e:
        return handle_error(e, "Error retrieving version history")


@bp.route("/models/<int:model_id>/revert/<int:version>", methods=["POST"])
@login_required
@admin_required
def revert_to_version(model_id: int, version: int):
    """
    Revert a model to a previous version (admin-only).
    """
    csrf_error = validate_csrf_token()
    if csrf_error:
        return csrf_error

    try:
        # Validate version number
        if version < 1:
            raise ValueError("Version must be a positive integer.")

        # Check if the version exists in the model's history
        versions = Model.get_version_history(model_id)
        if version not in [v["version"] for v in versions]:
            raise ValueError(f"Version {version} not found in model history.")

        logger.info(f"Reverting model {model_id} to version {version}")
        Model.revert_to_version(model_id, version)
        logger.info(f"Model {model_id} reverted to version {version} successfully")
        return jsonify(
            {"success": True, "message": "Model reverted to version successfully"}
        )
    except ValueError as e:
        return handle_error(e, "Error reverting model", 400)
    except Exception as e:
        return handle_error(e, "Unexpected error during model revert")