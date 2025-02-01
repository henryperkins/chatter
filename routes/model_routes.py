"""
Module for handling model routes.

This module provides routes for managing AI model configurations, including:
- CRUD operations for model records
- Model validation and configuration
- Version control and history tracking
- Default model management
"""

import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from flask import (
    Blueprint,
    jsonify,
    request,
    render_template,
    url_for,
    redirect,
    flash,
)
from flask_login import current_user
from flask_login import login_required
from flask_wtf.csrf import validate_csrf as flask_validate_csrf
from werkzeug.exceptions import HTTPException
import json
from config import Config
from models.provider import Provider
from utils.encryption import encrypt_api_key, EncryptionError
from decorators import admin_required
from forms import ModelForm
from database import db_session
from sqlalchemy import text
from models.model import Model

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
            request.headers.get("X-CSRFToken")
            or request.headers.get("X-CSRF-Token")
            or request.form.get("csrf_token")
            or (request.get_json(silent=True) or {}).get("csrf_token")
        )

        if not csrf_token:
            logger.warning(
                "CSRF token missing from request - Headers: %s, Form: %s, JSON: %s",
                request.headers,
                request.form,
                request.get_json(silent=True),
            )
            raise ValueError("CSRF token is required for this request.")

        # Validate the token
        flask_validate_csrf(csrf_token)
        logger.debug("CSRF token validated successfully")
        return None

    except ValueError as e:
        logger.warning("CSRF validation failed - missing token: %s", str(e))
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Security token is missing. Please refresh the page and try again.",
                }
            ),
            400,
        )

    except Exception as e:
        logger.error("CSRF validation failed: %s", str(e), exc_info=True)
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Invalid security token. Please refresh the page and try again.",
                }
            ),
            400,
        )


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
    data = {
        "provider_id": form.provider_id.data,
        "name": form.name.data,
        "deployment_name": form.deployment_name.data,
        "description": form.description.data,
        "api_endpoint": form.api_endpoint.data,
        "api_key": form.api_key.data,
        "temperature": form.temperature.data,
        "max_tokens": form.max_tokens.data,
        "max_completion_tokens": form.max_completion_tokens.data,
        "model_type": form.model_type.data,
        "requires_o1_handling": form.requires_o1_handling.data,
        "supports_streaming": form.supports_streaming.data,
        "is_default": form.is_default.data,
        "reasoning_effort": form.reasoning_effort.data,
        "store_completion": form.store.data,
    }
    return data


def validate_immutable_fields(model_id: int, data: dict) -> None:
    """
    Validate that immutable fields are not being updated.
    """
    immutable_fields = Model.get_immutable_fields(model_id)
    for field in immutable_fields:
        if field in data:
            raise ValueError(f"{field} is immutable and cannot be updated")


def validate_model_data(data: Dict[str, Any]) -> List[str]:
    """Validate model data before creation/update."""
    errors = []

    # Required fields
    required_fields = [
        "provider_id",
        "name",
        "deployment_name",
        "api_endpoint",
        "api_key",
    ]
    for field in required_fields:
        if not data.get(field):
            errors.append(f"Missing required field: {field}")

    # Get provider and its validation rules
    provider = Provider.get_by_id(data.get("provider_id"))
    if not provider:
        errors.append("Invalid provider_id")
        return errors

    # Basic HTTPS validation
    if data.get("api_endpoint"):
        if not data["api_endpoint"].startswith("https://"):
            errors.append("API endpoint must use HTTPS")

        # Get provider's validation rules
        validation_rules = provider.validation_rules
        if isinstance(validation_rules, str):
            validation_rules = json.loads(validation_rules)

        # For Azure providers
        if provider.is_azure:
            if not any(domain in data["api_endpoint"] for domain in ["openai.azure.com", "azure-api.net"]):
                errors.append("Must use a valid Azure OpenAI domain (*.openai.azure.com or *.azure-api.net)")
            if "/openai/deployments/" not in data["api_endpoint"]:
                errors.append("Must include /openai/deployments/{deployment-name}")
            if "api-version=" not in data["api_endpoint"]:
                errors.append("Must include api-version query parameter")
        # For other providers
        elif validation_rules.get("endpoint"):
            import re
            pattern = validation_rules["endpoint"]
            if not re.match(pattern, data["api_endpoint"]):
                errors.append(f"API endpoint must match provider's required format")

    # Validate model type specific requirements
    if data.get("requires_o1_handling"):
        if data.get("temperature", 1.0) != 1.0:
            errors.append("o1 models require temperature=1.0")
        if data.get("supports_streaming"):
            errors.append("o1 models do not support streaming")
        if data.get("max_completion_tokens", 0) > 8300:
            errors.append("Must be between 1-8300 for o1-preview models")

    return errors


def check_model_exists(db, name: str, deployment_name: str, provider_id: int) -> bool:
    """Check if a model with the given name or deployment_name already exists for the provider."""
    existing_model = db.execute(
        """SELECT COUNT(*) FROM models
        WHERE (name = :name OR deployment_name = :deployment_name)
        AND provider_id = :provider_id""",
        {"name": name, "deployment_name": deployment_name, "provider_id": provider_id},
    ).scalar()
    return existing_model > 0



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
                "provider_id": m.provider_id,
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
    """Create a new model (admin-only)."""
    start_time = datetime.now()
    csrf_error = validate_csrf_token()
    if csrf_error:
        return csrf_error

    form = ModelForm()
    if not form.validate_on_submit():
        logger.warning("Model form validation failed: %s", form.errors)
        return render_template("add_model.html", form=form, errors=form.errors)

    try:
        # Begin transaction
        with db_session() as db:
            # Extract and validate data
            data = extract_model_data(form)

            # Pre-validate model data
            validation_errors = validate_model_data(data)
            if validation_errors:
                return render_template(
                    "add_model.html", form=form, error=validation_errors[0]
                )

            # Check for duplicate names/deployments
            if check_model_exists(
                db, data["name"], data["deployment_name"], data["provider_id"]
            ):
                return render_template(
                    "add_model.html",
                    form=form,
                    error="Model with this name or deployment already exists",
                )

            # Encrypt API key
            try:
                data["api_key"] = encrypt_api_key(data["api_key"])
            except EncryptionError as e:
                logger.error(str(e))
                return render_template(
                    "add_model.html", form=form, error="Failed to secure API key"
                )

            # Validate model configuration
            Model.validate_model_config(data)

            # Create model
            model_id = Model.create(data)
            logger.info(
                "Model created",
                extra={
                    "model_id": model_id,
                    "model_name": data["name"],
                    "user_id": current_user.id,
                    "duration_ms": (datetime.now() - start_time).total_seconds() * 1000,
                },
            )

            # If this is first model, set as default
            model_count = db.execute("SELECT COUNT(*) FROM models").scalar()
            if model_count == 1:
                Model.set_default(model_id)
                logger.info("Set model %d as default", model_id)

            # Commit transaction
            db.commit()

        # Redirect to chat interface upon success
        return redirect(url_for("chat.chat_interface"))

    except Exception as e:
        logger.error("Error creating model: %s", str(e), exc_info=True)
        return render_template(
            "add_model.html",
            form=form,
            error="Failed to create model. Please try again.",
        )


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
        with db_session() as db:
            logger.info("Updating model with ID: %d", model_id)
            # Remove 'provider_id' from data as it is immutable
            if 'provider_id' in data:
                data.pop('provider_id', None)

            validate_immutable_fields(model_id, data)

            # Extract and validate data
            validation_errors = validate_model_data(data)
            if validation_errors:
                return jsonify({"error": validation_errors[0], "success": False}), 400

            # Update model within transaction
            Model.update(model_id, data)
            db.commit()
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
        with db_session() as db:
            logger.info("Deleting model with ID: %d", model_id)
            Model.delete(model_id)
            db.commit()
            logger.info("Model deleted successfully: %d", model_id)
            return jsonify({"success": True, "message": "Model deleted successfully"})

    except ValueError as e:
        return handle_error(e, f"Error deleting model {model_id}", 400)
    except Exception as e:
        return handle_error(e, f"Unexpected error during model deletion {model_id}")


@bp.route("/add-model", methods=["GET", "POST"])
@login_required
@admin_required
def add_model_page():
    """
    Render a page for adding a model.
    """
    form = ModelForm()

    # Populate provider choices
    form.provider_id.choices = [(p.id, p.name) for p in Provider.get_all()]
    
    # Pre-select provider if provider_id is provided
    provider_id = request.args.get('provider_id', type=int)
    provider = None
    if provider_id:
        provider = Provider.get_by_id(provider_id)
        if provider:
            form.provider_id.data = provider_id
            
            # Pre-fill form based on provider settings
            capabilities = provider.capabilities
            
            # Set temperature limits based on provider capabilities
            if 'temperature_range' in capabilities:
                temp_range = capabilities['temperature_range']
                form.temperature.data = temp_range.get('default', 1.0)
            
            # Set max tokens limit
            if 'max_tokens' in capabilities:
                form.max_tokens.data = capabilities['max_tokens']
                form.max_completion_tokens.data = min(
                    Config.DEFAULT_MAX_COMPLETION_TOKENS,
                    capabilities['max_tokens']
                )
            
            # Set streaming support
            form.supports_streaming.data = capabilities.get('streaming', False)
            
            # Pre-fill API endpoint using provider's stored base URL
            if provider.api_base_url:
                form.api_endpoint.data = provider.api_base_url
            elif provider.endpoint_pattern:
                # Fallback to pattern if no base URL is stored
                form.api_endpoint.data = provider.endpoint_pattern
            
            # Set API version
            if provider.api_version_format:
                form.api_version.data = provider.api_version_format
    
    if request.method == "POST":
        return create_model()
    
    logger.debug("Rendering add model page")
    return render_template(
        "add_model.html",
        form=form,
        provider=provider,
        DEFAULT_MAX_COMPLETION_TOKENS=Config.DEFAULT_MAX_COMPLETION_TOKENS,
    )


@bp.route("/edit/<int:model_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_model(model_id):
    """Edit model route handler with comprehensive validation and error handling."""
    try:
        model = Model.get_by_id(model_id)
        if not model:
            flash(f"Model with ID {model_id} not found", "error")
            return redirect(url_for('model.get_models'))

        provider = Provider.get_by_id(model.provider_id)
        form = ModelForm(request.form, obj=model)
        form.provider_id.choices = [(p.id, p.name) for p in Provider.get_all()]

        if request.method == "POST":
            # CSRF protection
            csrf_error = validate_csrf_token()
            if csrf_error:
                return csrf_error

            # Handle form data from both JSON and form submissions
            if request.is_json:
                form_data = request.get_json()
                # Convert JSON data to MultiDict format
                from werkzeug.datastructures import MultiDict
                form_data = MultiDict((k, v) for k, v in form_data.items())
            else:
                form_data = request.form
            form = ModelForm(form_data, obj=model)
            form.provider_id.choices = [(p.id, p.name) for p in Provider.get_all()]

            if not form.validate():
                error_messages = [f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()]
                flash(f"Validation errors: {'. '.join(error_messages)}", "error")
                return render_template("edit_model.html", form=form, model=model, provider=provider)

            # Prepare update data with proper type conversions
            update_data = {
                'provider_id': form.provider_id.data,
                'name': form.name.data.strip(),
                'deployment_name': form.deployment_name.data.strip(),
                'description': form.description.data.strip(),
                'api_endpoint': form.api_endpoint.data.rstrip('/'),
                'model_type': form.model_type.data,
                # Extract api_version from api_endpoint URL
                'api_version': (lambda url:
                    parse_qs(urlparse(url).query).get('api-version', [''])[0] if url else ''
                )(form.api_endpoint.data) or '2025-01-01-preview',  # Default if not found
                'temperature': float(form.temperature.data) if form.temperature.data not in [None, ''] else None,
                'max_tokens': int(form.max_tokens.data) if form.max_tokens.data not in [None, ''] else None,
                'max_completion_tokens': int(form.max_completion_tokens.data),
                'requires_o1_handling': bool(form.requires_o1_handling.data),
                'supports_streaming': bool(form.supports_streaming.data),
                'is_default': bool(form.is_default.data)
            }

            # Handle API key preservation
            if form.api_key.data.strip() == '':
                # Preserve existing encrypted key if field is empty
                update_data['api_key'] = model.api_key
            else:
                try:
                    # Encrypt new key if provided
                    update_data['api_key'] = encrypt_api_key(form.api_key.data)
                except EncryptionError as e:
                    logger.error(str(e))
                    flash("Failed to secure API key", "error")
                    return render_template(
                        "edit_model.html",
                        form=form,
                        model=model,
                        provider=provider,
                        DEFAULT_MAX_COMPLETION_TOKENS=Config.DEFAULT_MAX_COMPLETION_TOKENS
                    )

            # Get provider capabilities
            provider = Provider.get_by_id(form.provider_id.data)
            provider_max = provider.capabilities.get('max_tokens', 16384) if provider else 16384

            # Check if this is an o1-preview model
            model_type = update_data.get('model_type', '').lower()
            requires_o1 = update_data.get('requires_o1_handling', False)
            is_o1_preview = model_type == 'o1-preview' and requires_o1

            # Apply appropriate constraints
            if is_o1_preview:
                update_data.update({
                    'temperature': 1.0,
                    'supports_streaming': False,
                    'max_completion_tokens': min(update_data['max_completion_tokens'], 8300)
                })
            else:
                update_data['max_completion_tokens'] = min(
                    update_data['max_completion_tokens'],
                    provider_max
                )

            # Handle default model switching
            if update_data['is_default'] and not model.is_default:
                # Clear previous default
                current_default = Model.get_default()
                if current_default:
                    Model.update(current_default.id, {'is_default': False})

            # Perform the update with version tracking
            with db_session() as db:
                try:
                    # Create version snapshot
                    db.execute(
                        text("""
                            INSERT INTO model_versions
                            (model_id, version_data, created_at)
                            VALUES (:model_id, :version_data, NOW())
                        """),
                        {
                            'model_id': model_id,
                            'version_data': json.dumps(model.__dict__, default=str)
                        }
                    )

                    # Update main model record
                    Model.update(model_id, update_data)
                    db.commit()

                    flash("Model configuration updated successfully", "success")
                    return redirect(url_for('chat.chat_interface'))

                except ValueError as ve:
                    db.rollback()
                    if "Model was modified by another user" in str(ve):
                        # Handle version conflict
                        flash("This model was modified by another user. Please refresh the page and try again.", "error")
                        # Reload the model with fresh data
                        model = Model.get_by_id(model_id)
                        form = ModelForm(obj=model)
                        form.provider_id.choices = [(p.id, p.name) for p in Provider.get_all()]
                        return render_template(
                            "edit_model.html",
                            form=form,
                            model=model,
                            provider=provider,
                            DEFAULT_MAX_COMPLETION_TOKENS=Config.DEFAULT_MAX_COMPLETION_TOKENS
                        )
                    else:
                        flash(f"Validation error: {str(ve)}", "error")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Error updating model {model_id}: {str(e)}", exc_info=True)
                    flash("Failed to update model due to a server error", "error")

        return render_template(
            "edit_model.html",
            form=form,
            model=model,
            provider=provider,
            DEFAULT_MAX_COMPLETION_TOKENS=Config.DEFAULT_MAX_COMPLETION_TOKENS
        )

    except Exception as e:
        logger.error(f"Critical error in edit_model: {str(e)}", exc_info=True)
        flash("A system error occurred while processing your request", "error")
        return redirect(url_for('model.get_models'))


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
        with db_session() as db:
            logger.info("Setting model %d as default", model_id)
            Model.set_default(model_id)
            db.commit()
            logger.info("Model %d set as default successfully", model_id)
            return jsonify(
                {"success": True, "message": "Model set as default successfully"}
            )
    except Exception as e:
        return handle_error(e, "Unexpected error setting default model")


@bp.route("/api/providers/<int:provider_id>", methods=["GET"])
@login_required
def get_provider_details(provider_id: int):
    """
    Get provider details including capabilities for form configuration.
    """
    try:
        provider = Provider.get_by_id(provider_id)
        if not provider:
            return jsonify({"error": "Provider not found"}), 404
            
        return jsonify({
            "id": provider.id,
            "name": provider.name,
            "requires_authentication": provider.requires_authentication,
            "endpoint_pattern": provider.endpoint_pattern,
            "api_version_format": provider.api_version_format,
            "capabilities": provider.capabilities
        })
    except Exception as e:
        logger.error(f"Error retrieving provider details: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to retrieve provider details"}), 500

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
