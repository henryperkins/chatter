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

# Create a Config instance
config_instance = Config()
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
bp = Blueprint("model", __name__, url_prefix="/models")


# Helper Functions


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
    """Enhanced validation for model configuration."""
    errors = []

    # If the model type is explicitly "azure", perform simplified Azure-specific validations.
    if data.get("model_type") == "azure":
        required_azure_fields = [
            "api_endpoint",
            "deployment_name",
            "api_version",
            "api_key",
        ]
        for field in required_azure_fields:
            if not data.get(field):
                errors.append(f"Missing required Azure field: {field}")

        if data.get("api_endpoint") and "openai.azure.com" not in data["api_endpoint"]:
            errors.append("Azure endpoint must contain openai.azure.com")

    # Otherwise, perform the original provider-based validations.
    else:
        # Retrieve the provider for context-aware validation.
        provider = Provider.get_by_id(data.get("provider_id"))
        if not provider:
            errors.append("Invalid provider_id")
            return errors

        # Validate required base fields.
        base_required_fields = ["provider_id", "name", "api_endpoint", "api_key"]
        for field in base_required_fields:
            if not data.get(field):
                errors.append(f"Missing required field: {field}")

        # Special handling for deployment_name based on the provider type.
        if provider.is_azure:
            if not data.get("deployment_name"):
                errors.append("Deployment name is required for Azure OpenAI providers")
            elif not isinstance(data["deployment_name"], str):
                errors.append("Deployment name must be a string")
            elif not data["deployment_name"].strip():
                errors.append(
                    "Deployment name cannot be empty for Azure OpenAI providers"
                )
        elif data.get("deployment_name"):
            # Warn if deployment_name is provided for non-Azure providers.
            logger.warning(
                "Deployment name provided for non-Azure provider",
                extra={
                    "provider": provider.name,
                    "deployment_name": data["deployment_name"],
                },
            )

        # Basic API endpoint validation.
        if data.get("api_endpoint"):
            if not data["api_endpoint"].startswith("https://"):
                errors.append("API endpoint must use HTTPS")

            # Attempt to parse provider-specific validation rules if provided.
            validation_rules = provider.validation_rules
            if isinstance(validation_rules, str):
                try:
                    validation_rules = json.loads(validation_rules)
                except Exception:
                    errors.append("Invalid validation_rules format in provider")
                    validation_rules = {}

            # Dynamic API endpoint validation based on provider type.
            if provider.is_azure:
                if not any(
                    domain in data["api_endpoint"]
                    for domain in ["openai.azure.com", "azure-api.net"]
                ):
                    errors.append(
                        "Must use a valid Azure OpenAI domain (*.openai.azure.com or *.azure-api.net)"
                    )
                if "/openai/deployments/" not in data["api_endpoint"]:
                    errors.append("Must include /openai/deployments/{deployment-name}")
                if "api-version=" not in data["api_endpoint"]:
                    errors.append("Must include api-version query parameter")
            else:
                if (
                    "openai.azure.com" in data["api_endpoint"]
                    or "azure-api.net" in data["api_endpoint"]
                ):
                    errors.append(
                        "Must use standard OpenAI endpoint for non-Azure providers"
                    )
                if not data["api_endpoint"].startswith("https://api.openai.com/v1"):
                    errors.append(
                        "OpenAI endpoints must use format: https://api.openai.com/v1/..."
                    )

        # Validate model type–specific requirements for o1 handling.
        if data.get("requires_o1_handling"):
            if data.get("temperature", 1.0) != 1.0:
                errors.append("o1 models require temperature=1.0")
            if data.get("supports_streaming"):
                errors.append("o1 models do not support streaming")
            if data.get("max_completion_tokens", 0) > 32000:
                errors.append(
                    "max_completion_tokens must be between 1 and 32000 for o1-preview models"
                )

    # Validate token limits for all models.
    if data.get("max_completion_tokens", 0) > 128000:
        errors.append("max_completion_tokens cannot exceed 128,000")

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

    # Check if we have any form data
    if not (request.form or request.get_json()):
        logger.warning("Form submitted without data")
        flash("No form data received. Please fill out the form.", "error")
        return render_template(
            "add_model.html",
            form=ModelForm(),
            provider=None,
            DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS
        )

    # Handle form data from both JSON and form submissions
    if request.is_json:
        data = request.get_json()
        form = ModelForm(data=data)
    else:
        form = ModelForm(request.form)

    # Log form submission attempt
    logger.info("Model form submitted", extra={
        "method": "JSON" if request.is_json else "FORM",
        "has_data": True,
        "provider_id": form.provider_id.data if form.provider_id.data else None,
        "form_data": {k: v for k, v in (request.form or request.get_json() or {}).items() if k != 'api_key'}
    })

    # Log initial form data
    logger.info("Processing model creation request", extra={
        "form_data": {k: v for k, v in form.data.items() if k != 'api_key'},
        "provider_id": form.provider_id.data
    })

    # Validate the form
    if not form.validate():
        logger.error("Model form validation failed", extra={
            "form_errors": form.errors,
            "field_data": {
                field_name: {
                    "data": getattr(form, field_name).data,
                    "errors": getattr(form, field_name).errors
                } for field_name in form.data.keys()
            }
        })

        if request.is_json:
            return jsonify({"success": False, "errors": form.errors}), 400
        else:
            # Get provider from form data if available
            provider = Provider.get_by_id(form.provider_id.data) if form.provider_id.data else None
            if provider:
                logger.info("Provider found for form", extra={"provider_id": provider.id, "is_azure": provider.is_azure})
            else:
                logger.warning("No provider found for form")

            flash("Form validation failed. Please check the errors below.", "error")
            return render_template("add_model.html", form=form, errors=form.errors, provider=provider)

    try:
        # Begin transaction
        with db_session() as db:
            # Extract and validate data
            data = extract_model_data(form)

            # Get provider for validation context
            provider = Provider.get_by_id(data["provider_id"])
            if not provider:
                logger.error("Provider not found", extra={"provider_id": data["provider_id"]})
                flash("Invalid provider selected", "error")
                return render_template("add_model.html", form=form, provider=None)

            # Log validation context
            logger.info("Validating model data", extra={
                "provider": {
                    "id": provider.id,
                    "name": provider.name,
                    "is_azure": provider.is_azure
                },
                "deployment_name": {
                    "value": data["deployment_name"],
                    "required": provider.is_azure
                }
            })

            # Pre-validate model data
            validation_errors = validate_model_data(data)
            if validation_errors:
                logger.error("Model validation failed", extra={
                    "errors": validation_errors,
                    "data": {k: v for k, v in data.items() if k != 'api_key'}
                })

                if request.is_json:
                    return jsonify({"success": False, "errors": validation_errors}), 400
                else:
                    for error in validation_errors:
                        flash(error, "error")
                    return render_template(
                        "add_model.html", form=form, provider=provider
                    )

            # Special validation for deployment_name
            if provider.is_azure and not data["deployment_name"]:
                logger.error("Missing deployment_name for Azure provider")
                flash("Deployment name is required for Azure providers", "error")
                return render_template("add_model.html", form=form, provider=provider)

            # Check for duplicate names/deployments
            if check_model_exists(
                db, data["name"], data["deployment_name"], data["provider_id"]
            ):
                provider = Provider.get_by_id(form.provider_id.data) if form.provider_id.data else None
                return render_template(
                    "add_model.html",
                    form=form,
                    error="Model with this name or deployment already exists",
                    provider=provider
                )

            # Encrypt API key
            try:
                from config import Config
                data["api_key"] = encrypt_api_key(data["api_key"], Config().ENCRYPTION_KEY)
            except EncryptionError as e:
                logger.error(str(e))
                return render_template(
                    "add_model.html",
                    form=form,
                    error="Failed to secure API key",
                    provider=Provider.get_by_id(form.provider_id.data) if form.provider_id.data else None
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

        # Add success message and redirect
        flash(f"Model '{data['name']}' created successfully", "success")
        logger.info("Model creation successful, redirecting to chat interface", extra={
            "model_id": model_id,
            "model_name": data["name"]
        })
        return redirect(url_for("chat.chat_interface"))

    except ValueError as ve:
        logger.error("Validation error creating model: %s", str(ve), exc_info=True)
        flash(str(ve), "error")
        provider = Provider.get_by_id(form.provider_id.data) if form.provider_id.data else None
        return render_template(
            "add_model.html",
            form=form,
            provider=provider,
            DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS
        )
    except EncryptionError as ee:
        logger.error("Encryption error creating model: %s", str(ee), exc_info=True)
        flash("Failed to secure API key. Please try again.", "error")
        provider = Provider.get_by_id(form.provider_id.data) if form.provider_id.data else None
        return render_template(
            "add_model.html",
            form=form,
            provider=provider,
            DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS
        )
    except Exception as e:
        logger.error("Unexpected error creating model: %s", str(e), exc_info=True)
        flash("An unexpected error occurred. Please try again.", "error")
        provider = Provider.get_by_id(form.provider_id.data) if form.provider_id.data else None
        return render_template(
            "add_model.html",
            form=form,
            provider=provider,
            DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS
        )


@bp.route("/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def update_model(model_id: int):
    """
    Update an existing model (admin-only).
    """
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
    try:
        # Get all providers first
        providers = Provider.get_all()
        if not providers:
            logger.error("No providers available")
            flash("No providers available. Please add a provider first.", "error")
            return redirect(url_for("chat.chat_interface"))

        # Create form with default values
        form = ModelForm()
        form.provider_id.choices = [(p.id, p.name) for p in providers]

        # Log initial form state
        logger.info("Initializing add model form", extra={
            "provider_count": len(providers),
            "provider_choices": form.provider_id.choices
        })

        # Pre-select provider if provider_id is provided
        provider_id = request.args.get('provider_id', type=int)
        provider = None
        if provider_id:
            provider = Provider.get_by_id(provider_id)
            if provider:
                form.provider_id.data = provider_id
                logger.debug("Pre-selected provider", extra={
                    "provider_id": provider_id,
                    "provider_name": provider.name
                })

                # Pre-fill form based on provider settings
                capabilities = provider.capabilities
                logger.debug("Provider capabilities", extra={"capabilities": capabilities})

                # Set temperature limits based on provider capabilities
                if 'temperature_range' in capabilities:
                    temp_range = capabilities['temperature_range']
                    form.temperature.data = temp_range.get('default', 1.0)
                    logger.debug("Set temperature", extra={"default_temp": form.temperature.data})

                # Set max tokens limit
                if 'max_tokens' in capabilities:
                    form.max_tokens.data = capabilities['max_tokens']
                    form.max_completion_tokens.data = min(
                        config_instance.DEFAULT_MAX_COMPLETION_TOKENS,
                        capabilities['max_tokens']
                    )
                    logger.debug("Set token limits", extra={
                        "max_tokens": form.max_tokens.data,
                        "max_completion_tokens": form.max_completion_tokens.data
                    })

                # Set streaming support
                form.supports_streaming.data = capabilities.get('streaming', False)
                logger.debug("Set streaming support", extra={"streaming": form.supports_streaming.data})

                # Pre-fill API endpoint using provider's stored base URL
                if provider.api_base_url:
                    form.api_endpoint.data = provider.api_base_url
                    logger.debug("Using provider base URL", extra={"url": form.api_endpoint.data})
                elif provider.endpoint_pattern:
                    # Fallback to pattern if no base URL is stored
                    form.api_endpoint.data = provider.endpoint_pattern
                    logger.debug("Using provider endpoint pattern", extra={"pattern": form.api_endpoint.data})

                # Set API version
                if provider.api_version_format:
                    form.api_version.data = provider.api_version_format
                    logger.debug("Set API version", extra={"version": form.api_version.data})

        if request.method == "POST":
            return create_model()

        logger.debug("Rendering add model page")
        return render_template(
            "add_model.html",
            form=form,
            provider=provider,
            DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS,
        )

    except Exception as e:
        logger.error("Error preparing add model page", exc_info=True)
        flash("An error occurred while preparing the form. Please try again.", "error")
        return redirect(url_for("chat.chat_interface"))


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
                    update_data['api_key'] = encrypt_api_key(form.api_key.data, Config().ENCRYPTION_KEY)
                except EncryptionError as e:
                    logger.error(str(e))
                    flash("Failed to secure API key", "error")
                    return render_template(
                        "edit_model.html",
                        form=form,
                        model=model,
                        provider=provider,
                        DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS
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
                    'max_completion_tokens': min(update_data['max_completion_tokens'], 32000)
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
                    # Get existing model for api_key handling
                    existing_model = Model.get_by_id(model_id)
                    if not existing_model:
                        raise ValueError(f"Model with ID {model_id} not found")

                    # If api_key is empty/None, preserve existing encrypted key
                    if "api_key" in update_data and not update_data["api_key"].strip():
                        update_data["api_key"] = existing_model.api_key

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
                            DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS
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
            DEFAULT_MAX_COMPLETION_TOKENS=config_instance.DEFAULT_MAX_COMPLETION_TOKENS
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
            "capabilities": provider.capabilities,
            "is_azure": provider.is_azure
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
