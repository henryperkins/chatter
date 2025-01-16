"""
Module for handling model routes.

This module provides routes for managing AI model configurations, including:
- CRUD operations for model records
- Model validation and configuration
- Version control and history tracking
- Default model management
"""

import logging
from typing import Optional

from flask import (
    Blueprint,
    jsonify,
    request,
    render_template,
    url_for,
    redirect,
)
from flask_login import login_required
from flask_wtf.csrf import validate_csrf as flask_validate_csrf
from werkzeug.exceptions import HTTPException

from decorators import admin_required
from forms import ModelForm
from models import Model

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Define the Blueprint for model routes
bp = Blueprint("model", __name__)


# Helper Functions
def validate_csrf_token() -> Optional[tuple]:
    """Validate CSRF token for all POST, PUT, and DELETE requests.
    Checks for token in:
    - X-CSRFToken header
    - X-CSRF-Token header
    - Form data (csrf_token)
    - JSON body (csrf_token)
    """
    try:
        # Try to get token from multiple locations
        csrf_token = (
            request.headers.get("X-CSRFToken") or
            request.headers.get("X-CSRF-Token") or
            request.form.get("csrf_token") or
            (request.get_json(silent=True) or {}).get("csrf_token")
        )

        if not csrf_token:
            logger.warning(
                "CSRF token missing from request - Headers: %s, Form: %s, JSON: %s",
                request.headers,
                request.form,
                request.get_json(silent=True)
            )
            raise ValueError("CSRF token is required for this request.")

        # Validate the token
        flask_validate_csrf(csrf_token)
        logger.debug("CSRF token validated successfully")
        return None
        
    except ValueError as e:
        logger.warning("CSRF validation failed - missing token: %s", str(e))
        return jsonify({
            "success": False,
            "error": "Security token is missing. Please refresh the page and try again."
        }), 400
        
    except Exception as e:
        logger.error("CSRF validation failed: %s", str(e), exc_info=True)
        return jsonify({
            "success": False,
            "error": "Invalid security token. Please refresh the page and try again."
        }), 400


def handle_error(error: Exception, message: str, status_code: int = 500) -> tuple:
    """Handle errors with proper logging and responses."""
    if isinstance(error, ValueError):
        status_code = 400
    elif isinstance(error, HTTPException):
        status_code = error.code

    logger.error(f"{message}: {str(error)}", exc_info=True)
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
        logger.info(
            "Retrieved %d models with offset %d and limit %d",
            len(model_list),
            offset,
            limit,
        )
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
    if form.validate_on_submit():
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
            logger.info("Model created successfully with ID: %d", model_id)
            # Redirect to chat interface upon success
            return redirect(url_for('chat.chat_interface'))

        except ValueError as e:
            logger.error("Validation error during model creation: %s", str(e))
            return render_template("add_model.html", form=form, error=str(e))
        except Exception as e:
            logger.error("Unexpected error during model creation: %s", str(e), exc_info=True)
            return render_template("add_model.html", form=form, error="An unexpected error occurred.")
    else:
        logger.warning("Model form validation failed: %s", form.errors)
        return render_template("add_model.html", form=form, errors=form.errors)


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
        logger.warning("No data provided for updating model %d", model_id)
        return jsonify({"error": "No data provided", "success": False}), 400

    try:
        logger.info("Updating model with ID: %d", model_id)
        validate_immutable_fields(model_id, data)
        Model.update(model_id, data)
        logger.info("Model updated successfully: %d", model_id)
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
        logger.info("Deleting model with ID: %d", model_id)
        Model.delete(model_id)
        logger.info("Model deleted successfully: %d", model_id)
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
    logger.debug("Rendering add model page")
    return render_template("add_model.html", form=form)


@bp.route("/edit/<int:model_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_model(model_id):
    """Edit model route handler."""
    try:
        model = Model.get_by_id(model_id)
        if not model:
            logger.warning("Model with ID %d not found in database", model_id)
            return jsonify({
                "error": "Model not found",
                "message": f"No model found with ID {model_id}"
            }), 404

        form = ModelForm(obj=model)

        if request.method == "POST":
            # Validate CSRF first
            csrf_error = validate_csrf_token()
            if csrf_error:
                return csrf_error

            # Handle JSON data
            if request.is_json:
                form_data = request.get_json()
            else:
                form_data = request.form

            # Bind and validate form
            form = ModelForm(data=form_data)
            
            if not form.validate():
                logger.warning("Form validation failed: %s", form.errors)
                return jsonify({
                    "success": False,
                    "errors": form.errors,
                    "message": "Form validation failed"
                }), 400
            
            if not form.validate():
                logger.warning("Form validation failed: %s", form.errors)
                return jsonify({
                    "error": form.errors,
                    "message": "Form validation failed",
                    "success": False
                }), 400

            # Extract and validate data
            data = extract_model_data(form)
            # Handle null/empty values for numeric fields
            for field in ['max_tokens', 'max_completion_tokens', 'temperature']:
                value = data.get(field)
                if value is None or value == '':
                    data[field] = None
                elif isinstance(value, str):
                    try:
                        if field == 'temperature':
                            data[field] = float(value)
                        else:
                            data[field] = int(value)
                    except (ValueError, TypeError):
                        data[field] = None
                    
            logger.debug("Extracted model data: %s", {
                k: v if k != "api_key" else "****" for k, v in data.items()
            })
            validate_immutable_fields(model_id, data)
            
            # Handle o1-preview model constraints
            if data.get('requires_o1_handling'):
                if data.get('supports_streaming', False):
                    raise ValueError("o1-preview models do not support streaming")
                data['temperature'] = 1.0  # Force temperature for o1-preview
                data['supports_streaming'] = False  # Force disable streaming
                logger.info("Enforcing o1-preview constraints for model %d", model_id)
            
            # Handle is_default setting
            if data.get('is_default'):
                Model.set_default(model_id)
                logger.info("Set model %d as default", model_id)
            else:
                # If unsetting default, ensure another model is set as default
                current_default = Model.get_default()
                if current_default and current_default.id == model_id:
                    # Find another model to set as default
                    other_models = Model.get_all(limit=1)
                    if other_models:
                        Model.set_default(other_models[0].id)
                    else:
                        raise ValueError("Cannot unset default model - no other models exist")
            
            # Validate model configuration
            Model.validate_model_config(data)
            
            # Update model with validated data
            Model.update(model_id, data)
            logger.info("Model updated successfully: %d", model_id)
            
            redirect_url = url_for('chat.chat_interface', _external=True)
            logger.debug("Sending response with redirect: %s", {
                "success": True,
                "message": "Model updated successfully",
                "redirect": redirect_url
            })
            return jsonify({
                "success": True,
                "message": "Model updated successfully",
                "redirect": redirect_url
            })

        logger.debug("Rendering edit model page for model ID %d", model_id)
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
        logger.info("Setting model %d as default", model_id)
        Model.set_default(model_id)
        logger.info("Model %d set as default successfully", model_id)
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
        logger.info("Retrieved immutable fields for model ID %d", model_id)
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
        logger.info("Retrieved version history for model ID %d", model_id)
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

        logger.info("Reverting model %d to version %d", model_id, version)
        Model.revert_to_version(model_id, version)
        logger.info("Model %d reverted to version %d successfully", model_id, version)
        return jsonify(
            {"success": True, "message": "Model reverted to version successfully"}
        )
    except ValueError as e:
        return handle_error(e, "Error reverting model", 400)
    except Exception as e:
        return handle_error(e, "Unexpected error during model revert")
