import re
import logging
from flask_wtf import FlaskForm
from flask import request

from wtforms import (
    StringField,
    PasswordField,
    FloatField,
    Field,
    IntegerField,
    BooleanField,
    TextAreaField,
    SelectField,
    URLField,
    ValidationError,
    SubmitField,
    HiddenField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    EqualTo,
    NumberRange,
    URL,
    Optional,
    Regexp,
)
from typing import Any
from sqlalchemy import text

from models.provider import Provider
from models.model import Model
from utils.encryption import encrypt_api_key, EncryptionError
from chat_utils import validate_password_strength
import logging

logger = logging.getLogger(__name__)
from database import db_session, is_initialized

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------
# Custom Fields: NullableIntegerField, NullableFloatField
# ------------------------------------------------------------------------

class NullableIntegerField(IntegerField):
    """
    A custom IntegerField that treats empty or invalid input as None.
    """

    def process_formdata(self, valuelist):
        """Process form data for NullableIntegerField."""
        if valuelist and valuelist[0]:
            try:
                self.data = int(valuelist[0])
            except (ValueError, TypeError):
                self.data = None
        else:
            self.data = None

class NullableFloatField(FloatField):
    """
    A custom FloatField that treats empty or invalid input as None.
    """

    def process_formdata(self, valuelist):
        if valuelist and valuelist[0]:
            try:
                self.data = float(valuelist[0])
            except (ValueError, TypeError):
                self.data = None
        else:
            self.data = None

# ------------------------------------------------------------------------
# LoginForm
# ------------------------------------------------------------------------

class LoginForm(FlaskForm):
    """
    Form for user login.
    """

    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Username is required."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
        ],
    )
    remember = BooleanField("Remember Me", default=False)
    submit = SubmitField("Login")

    def validate_username(self, field: Field) -> None:
        """
        Check for too many failed login attempts before allowing another try.
        """
        try:
            with db_session() as db:
                try:
                    # Check recent failed attempts within the past 15 minutes
                    recent_failures = db.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM login_attempts
                            WHERE username = :username
                            AND success = false
                            AND attempted_at > NOW() - INTERVAL '15 minutes'
                            """
                        ),
                        {"username": field.data.strip()},
                    ).scalar()

                    if recent_failures >= 5:
                        raise ValidationError(
                            "Too many failed login attempts. Please try again in 15 minutes."
                        )
                except Exception as table_error:
                    # Handle case where login_attempts table doesn't exist yet
                    if "relation" in str(table_error) and "does not exist" in str(table_error):
                        logger.warning("Login attempts table does not exist - skipping rate limit check")
                        return
                    # Re-raise other database errors
                    raise
        except Exception as e:
            logger.error(f"Error checking login attempts: {str(e)}")
            # Don't expose internal errors to user
            raise ValidationError(
                "Unable to process login at this time. Please try again later."
            )

# ------------------------------------------------------------------------
# RegistrationForm
# ------------------------------------------------------------------------

class RegistrationForm(FlaskForm):
    """
    Form for user registration.
    Inherits CSRF protection from FlaskForm.
    """
    class Meta:
        csrf = True  # Explicitly enable CSRF protection

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if request and request.is_json:
            # For JSON requests, accept CSRF token from either body or header
            token = request.headers.get('X-CSRFToken') or (request.get_json() or {}).get('csrf_token')
            if token:
                self.csrf_token.data = token

    def validate_csrf_token(self, field):
        """Custom CSRF validation for both form and JSON submissions"""
        if request.is_json:
            token = request.headers.get('X-CSRFToken') or (request.get_json() or {}).get('csrf_token')
            if not token:
                raise ValidationError('CSRF token missing')
            if not field.current_token:
                raise ValidationError('CSRF session token missing')
            if not field.validate(token):
                raise ValidationError('CSRF token invalid')
            return True
        return super().validate_csrf_token(field)

    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Username is required."),
            Length(
                min=4, max=20, message="Username must be between 4 and 20 characters."
            ),
            Regexp(
                r"^[a-zA-Z0-9_]+$",
                message="Username can only contain letters, numbers, and underscores.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Invalid email address."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
            Length(min=8, message="Password must be at least 8 characters long."),
            Regexp(
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).+$",
                message="Password must include uppercase, lowercase, digit, and special character.",
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Register")

    def validate_username(self, field: Field) -> None:
        """
        Custom validator for username.
        Checks if username or email is already taken, plus format checks.
        """
        if not field.data:
            return
        username = field.data.strip()

        if not is_initialized():
            logger.warning("Database not initialized - skipping username validation")
            return

        try:
            with db_session(transactional=True) as db:
                # Check if username already exists
                if db.execute(
                    text("SELECT 1 FROM users WHERE username = :uname"),
                    {"uname": username},
                ).scalar():
                    raise ValidationError("This username is already taken. Please choose a different username.")

            # Validate username format
            if field.data != username:
                raise ValidationError(
                    "Username cannot contain leading or trailing spaces."
                )

            if len(username) < 4:
                raise ValidationError("Username must be at least 4 characters long.")

            if not re.match(r"^[a-zA-Z0-9_]+$", username):
                raise ValidationError(
                    "Username can only contain letters, numbers, and underscores."
                )

        except Exception as e:
            logger.error(f"Error validating username: {str(e)}", exc_info=True)
            raise ValidationError("An unexpected error occurred while validating the username. Please try again later.")

    def validate_email(self, field: Field) -> None:
        """
        Custom validator for email. Checks if email is already registered.
        """
        if not field.data:
            raise ValidationError("Email is required")

        email = field.data.lower().strip()

        try:
            with db_session() as db:
                if db.execute(
                    text("SELECT email FROM users WHERE LOWER(email) = :email"),
                    {"email": email},
                ).fetchone():
                    raise ValidationError("This email address is already registered. Please use a different email or try logging in.")

        except Exception as e:
            if isinstance(e, ValidationError):
                logger.error(f"Email validation failed: {str(e)}", exc_info=True)
                raise e
            logger.error(f"Error validating email: {str(e)}", exc_info=True)
            raise ValidationError("An error occurred while validating the email. Please try again later.")

    def validate_password(self, field: Field) -> None:
        """
        Validate password strength using a custom function.
        """
        if not field.data:
            raise ValidationError("Password is required")

        try:
            validate_password_strength(field.data)
        except ValidationError as e:
            raise e
        except Exception as e:
            logger.error(f"Error validating password: {str(e)}")
            raise ValidationError("Unable to validate password at this time")

# ------------------------------------------------------------------------
# ResetPasswordForm
# ------------------------------------------------------------------------

class ResetPasswordForm(FlaskForm):
    """
    Form for resetting password.
    """
    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(message="Password is required."),
            Length(min=8, message="Password must be at least 8 characters long."),
            Regexp(
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).+$",
                message="Password must include uppercase, lowercase, digit, and special character.",
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Reset Password")

# ------------------------------------------------------------------------
# ForgotPasswordForm
# ------------------------------------------------------------------------

class ForgotPasswordForm(FlaskForm):
    """
    Form for requesting a password reset.
    """
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Invalid email address."),
        ],
    )
    submit = SubmitField("Reset Password")

# ------------------------------------------------------------------------
# ProviderForm
# ------------------------------------------------------------------------

class ProviderForm(FlaskForm):
    """
    Form for creating or updating AI providers.
    """

    name = StringField(
        "Provider Name",
        validators=[
            DataRequired(message="Provider name is required."),
            Length(max=50, message="Provider name cannot exceed 50 characters."),
            Regexp(
                r"^[a-zA-Z0-9_\-\s]+$",
                message="Provider name can only contain letters, numbers, spaces, underscores, and hyphens.",
            ),
        ],
    )

    slug = StringField(
        "Provider Slug",
        validators=[
            DataRequired(message="Provider slug is required."),
            Length(max=50, message="Provider slug cannot exceed 50 characters."),
            Regexp(
                r"^[a-z0-9-]+$",
                message="Slug can only contain lowercase letters, numbers, and hyphens.",
            ),
        ],
    )

    api_base_url = URLField(
        "API Base URL",
        validators=[
            DataRequired(message="API base URL is required."),
            URL(message="Must be a valid URL.")
        ],
        description="Base URL for your OpenAI-compatible API (e.g., https://api.openai.com/v1)"
    )

    requires_authentication = BooleanField("Requires Authentication", default=True)

    endpoint_pattern = StringField(
        "API Path",
        validators=[
            DataRequired(message="API path is required."),
            Length(max=255, message="API path cannot exceed 255 characters."),
            Regexp(r"^/.*$", message="API path must start with /")
        ],
        default="/chat/completions",
        description="API path that will be appended to the base URL. Defaults to /chat/completions for OpenAI compatibility."
    )

    def validate_endpoint_pattern(self, field):
        """Validate the API path format."""
        try:
            # Don't allow Azure OpenAI patterns
            if 'azure' in self.slug.data.lower():
                raise ValidationError("Azure OpenAI endpoints should be configured through the Azure provider type")

            # Ensure path starts with /
            if not field.data.startswith('/'):
                raise ValidationError("API path must start with /")

            # Validate no double slashes
            if '//' in field.data:
                raise ValidationError("API path cannot contain double slashes")

        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Error validating API path: {str(e)}")

    def validate_api_base_url(self, field):
        """Validate the API base URL."""
        try:
            # Don't allow Azure OpenAI URLs
            if 'azure' in field.data.lower():
                raise ValidationError("Azure OpenAI endpoints should be configured through the Azure provider type")

            # Remove trailing slash
            field.data = field.data.rstrip('/')

        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Error validating API base URL: {str(e)}")

    api_version_format = StringField(
        "API Version Format",
        validators=[
            DataRequired(message="API version format is required."),
            Length(max=20, message="API version format cannot exceed 20 characters."),
            Regexp(
                r"^\d{4}-\d{2}-\d{2}(?:-preview)?$",
                message="API version format must be in format YYYY-MM-DD or YYYY-MM-DD-preview",
            ),
        ],
        default="2024-12-01-preview"
    )

    api_key = PasswordField(
        "API Key",
        validators=[
            Optional(),
            Length(min=32, message="API key must be at least 32 characters if provided.")
        ],
        description="Provider-level API key (if using a shared key)"
    )

    model_name = StringField(
        "Default Model Name",
        validators=[
            Optional(),
            Length(max=50, message="Model name cannot exceed 50 characters."),
            Regexp(
                r"^[a-zA-Z0-9_\-\s]+$",
                message="Model name can only contain letters, numbers, spaces, underscores, and hyphens.",
            ),
        ],
        description="Default model name for this provider"
    )

    deployment_name = StringField(
        "Default Deployment Name",
        validators=[
            Optional(),
            Length(max=50, message="Deployment name cannot exceed 50 characters."),
            Regexp(
                r"^[a-zA-Z0-9_\-]+$",
                message="Deployment name can only contain letters, numbers, underscores, and hyphens.",
            ),
        ],
        description="Default deployment name (Azure OpenAI only)"
    )

    is_azure = BooleanField(
        "Azure OpenAI Provider",
        default=False,
        description="Check if this is an Azure OpenAI provider"
    )

# ------------------------------------------------------------------------
# ModelForm
# ------------------------------------------------------------------------

class ModelForm(FlaskForm):
    name = StringField('Model Name', validators=[DataRequired(), Length(max=255)])
    deployment_name = StringField(
        'Deployment Name',
        validators=[Optional(), Length(max=255)],
        description="Required for Azure OpenAI providers. Leave empty for other providers.",
        render_kw={
            "class": "w-full border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-800 dark:text-gray-200"
        }
    )
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    provider_id = SelectField('Provider', coerce=int, validators=[DataRequired()])
    api_key = PasswordField('API Key', validators=[DataRequired(), Length(min=32, message="API key must be at least 32 characters.")])
    model_type = SelectField('Model Type',
        choices=[
            ('azure', 'Azure OpenAI (Standard)'),
            ('o1', 'Azure OpenAI (o1)'),
            ('o1-mini', 'Azure OpenAI (o1-mini)'),
            ('o1-preview', 'Azure OpenAI (o1-preview)'),
            ('o3-mini', 'Azure OpenAI (o3-mini)')
        ],
        validators=[DataRequired()],
        description="Select the model type - o1/o3 models support advanced reasoning capabilities"
    )

    reasoning_effort = SelectField('Reasoning Effort',
        choices=[
            ('low', 'Low - Faster responses, fewer tokens'),
            ('medium', 'Medium - Balanced speed and reasoning (Default)'),
            ('high', 'High - More thorough reasoning, more tokens')
        ],
        default='medium',
        validators=[Optional()],
        description="Controls how many reasoning tokens the model generates before responding"
    )

    store = BooleanField('Store Completion',
        default=False,
        description="Whether to store this completion for future reference"
    )
    max_completion_tokens = IntegerField('Max Completion Tokens', validators=[DataRequired(), NumberRange(min=1)])
    max_tokens = IntegerField('Max Tokens', validators=[Optional(), NumberRange(min=1)])
    temperature = FloatField('Temperature', validators=[Optional(), NumberRange(min=0.0, max=2.0)])
    top_p = FloatField('Top P', validators=[Optional(), NumberRange(min=0.0, max=1.0)])
    frequency_penalty = FloatField('Frequency Penalty', validators=[Optional(), NumberRange(min=-2.0, max=2.0)])
    presence_penalty = FloatField('Presence Penalty', validators=[Optional(), NumberRange(min=-2.0, max=2.0)])
    is_default = BooleanField('Default Model')
    supports_streaming = BooleanField('Streaming Support')
    requires_o1_handling = BooleanField('Requires o1-preview Handling')
    model_family = StringField('Model Family', validators=[Optional(), Length(max=255)])
    api_version = StringField('API Version', validators=[
        DataRequired(message="API version is required."),
        Length(max=20, message="API version cannot exceed 20 characters."),
        Regexp(
            r"^\d{4}-\d{2}-\d{2}(?:-preview)?$",
            message="API version must be in format YYYY-MM-DD or YYYY-MM-DD-preview"
        )
    ], default="2024-12-01-preview")
    version = HiddenField('Version')
    api_endpoint = URLField('API Endpoint', validators=[
        DataRequired(message="API endpoint is required."),
        URL(message="Must be a valid URL."),
    ])

    def __init__(self, *args, **kwargs):
        self.is_edit = kwargs.pop('is_edit', False)
        self.provider_validation_rules = {}  # Initialize here

        super().__init__(*args, **kwargs)

        # Log initialization
        logger.debug("Initializing ModelForm", extra={
            "is_edit": self.is_edit,
            "has_data": bool(args and args[0])
        })

        self.setup_edit_mode()
        self.load_providers()
        self.load_provider_validation_rules()

        # Get provider if available
        provider = None
        if self.provider_id.data:
            provider = Provider.get_by_id(self.provider_id.data)
            logger.debug("Found provider", extra={
                "provider_id": self.provider_id.data,
                "provider_name": provider.name if provider else None,
                "is_azure": provider.is_azure if provider else None
            })

        # Setup deployment_name field
        self.setup_deployment_name_field(provider)

        # Log form state after initialization
        logger.debug("Form initialized", extra={
            "deployment_name_state": {
                "value": self.deployment_name.data if hasattr(self, 'deployment_name') else None,
                "required": getattr(self.deployment_name, 'flags', {}).required if hasattr(self, 'deployment_name') else None,
                "render_kw": getattr(self.deployment_name, 'render_kw', {}) if hasattr(self, 'deployment_name') else None
            }
        })

        # Set default False for unchecked booleans
        for field in ['requires_o1_handling', 'supports_streaming', 'is_default']:
            if field not in self.data:
                setattr(self, field, False)

    def load_provider_validation_rules(self):
        """
        Load validation rules based on the selected provider and update field requirements.
        """
        provider_id = self.provider_id.data
        logger.debug("Loading provider validation rules", extra={"provider_id": provider_id})

        if not provider_id:
            logger.debug("No provider_id, skipping validation rules")
            self.provider_validation_rules = {}
            return

        provider = Provider.get_by_id(provider_id)
        if provider is None:
            logger.warning("Provider not found", extra={"provider_id": provider_id})
            self.provider_validation_rules = {}
            return

        # Load validation rules
        try:
            rules = provider.validation_rules
            if isinstance(rules, str):
                import json
                rules = json.loads(rules)
            logger.debug("Loaded provider validation rules", extra={
                "provider": provider.name,
                "rules": rules
            })
        except Exception as e:
            logger.error("Error loading validation rules", exc_info=True)
            rules = {}

        # Update deployment_name field based on provider type
        if provider.is_azure:
            logger.debug("Setting up Azure provider validation")
            # Make deployment_name required for Azure
            self.deployment_name.validators = [DataRequired(), Length(max=255)]
            if hasattr(self.deployment_name, 'flags'):
                self.deployment_name.flags.required = True
            if not hasattr(self.deployment_name, 'render_kw'):
                self.deployment_name.render_kw = {}
            self.deployment_name.render_kw['required'] = 'required'
            self.deployment_name.render_kw['aria-required'] = 'true'
        else:
            logger.debug("Setting up non-Azure provider validation")
            # Make deployment_name optional for non-Azure
            self.deployment_name.validators = [Optional(), Length(max=255)]
            if hasattr(self.deployment_name, 'flags'):
                self.deployment_name.flags.required = False
            if not hasattr(self.deployment_name, 'render_kw'):
                self.deployment_name.render_kw = {}
            self.deployment_name.render_kw.pop('required', None)
            self.deployment_name.render_kw.pop('aria-required', None)

        # Store the rules
        self.provider_validation_rules = rules

    def setup_edit_mode(self):
        """Modify form behavior for edit mode"""
        if self.is_edit:
            # Make API key optional for edits
            self.api_key.validators = [
                Optional(),
                Length(min=32, message="API key must be at least 32 characters if provided.")
            ]
            self.api_key.description = "Leave blank to keep existing key"
            self.api_key.flags.required = False

    def load_providers(self):
        """Dynamic provider loading with error handling"""
        try:
            with db_session() as session:
                providers = session.execute(
                    text("SELECT id, name FROM providers ORDER BY name")
                ).mappings().fetchall()
                self.provider_id.choices = [(p['id'], p['name']) for p in providers]
        except Exception as e:
            logger.error(f"Error loading providers: {str(e)}")
            self.provider_id.choices = []

    def validate_max_completion_tokens(self, field):
        """Enhanced validation with provider constraints"""
        try:
            value = int(field.data)
        except (TypeError, ValueError):
            raise ValidationError("Must be a valid integer")

        provider = Provider.get_by_id(self.provider_id.data)
        provider_max = provider.capabilities.get('max_tokens', 16384) if provider else 16384

        if self.requires_o1_handling.data:
            if not (1 <= value <= 25000):
                raise ValidationError("Must be between 1-25000 for o1-preview models (OpenAI recommended)")
        else:
            if not (1 <= value <= provider_max):
                raise ValidationError(f"Must be between 1-{provider_max} for this provider")

    def validate_temperature(self, field):
        """Temperature validation with o1-preview locking"""
        if self.requires_o1_handling.data:
            field.data = 1.0  # Force value for o1-preview
            return

        if field.data is None:
            return

        try:
            temp = float(field.data)
            if not (0 <= temp <= 2):
                raise ValidationError("Must be between 0.0 and 2.0")
        except ValueError:
            raise ValidationError("Must be a valid number")

    def validate_supports_streaming(self, field):
        """Streaming validation with o1-preview constraint"""
        if self.requires_o1_handling.data and field.data:
            raise ValidationError("Streaming not supported for o1-preview models")

    def process_api_key(self):
        """Handle API key encryption and preservation"""
        if self.is_edit and not self.api_key.data:
            # Preserve existing encrypted key
            original_model = Model.get_by_id(self._obj.id) if self._obj else None
            if original_model:
                self.api_key.data = original_model.api_key
        elif self.api_key.data:
            # Encrypt new key
            try:
                self.api_key.data = encrypt_api_key(self.api_key.data)
            except EncryptionError as e:
                logger.error(f"API key encryption failed: {str(e)}")
                raise ValidationError("Failed to secure API key")

    def validate_api_endpoint(self, field):
        if not field.data:
            return

        pattern = self.provider_validation_rules.get('endpoint')
        if pattern:
            import re
            if not re.match(pattern, field.data):
                raise ValidationError("API endpoint does not match the required format specified by the provider.")

    def setup_deployment_name_field(self, provider=None):
        """
        Configure the deployment_name field based on provider type.
        """
        if not hasattr(self, 'deployment_name'):
            return

        if provider is None and self.provider_id.data:
            provider = Provider.get_by_id(self.provider_id.data)

        logger.debug("Setting up deployment_name field", extra={
            "provider": provider.name if provider else None,
            "is_azure": provider.is_azure if provider else None
        })

        # Configure field attributes
        if not self.deployment_name.render_kw:
            self.deployment_name.render_kw = {}

        if provider and provider.is_azure:
            self.deployment_name.validators = [DataRequired(), Length(max=255)]
            self.deployment_name.flags.required = True
            self.deployment_name.render_kw.update({
                'required': 'required',
                'aria-required': 'true',
                'tabindex': '0'
            })
        else:
            self.deployment_name.validators = [Optional(), Length(max=255)]
            self.deployment_name.flags.required = False
            self.deployment_name.render_kw.update({
                'tabindex': '-1'
            })
            # Remove required attributes
            self.deployment_name.render_kw.pop('required', None)
            self.deployment_name.render_kw.pop('aria-required', None)

    def validate_deployment_name(self, field):
        """
        Enhanced validation for deployment_name field with detailed logging.
        """
        from models.provider import Provider
        provider = Provider.get_by_id(self.provider_id.data)

        # Log validation context
        logger.info("Validating deployment_name", extra={
            "field_value": field.data,
            "provider": provider.name if provider else None,
            "is_azure": provider.is_azure if provider else None,
            "field_required": bool(provider and provider.is_azure),
            "field_attributes": {
                "required": getattr(field, 'flags', {}).required,
                "render_kw": getattr(field, 'render_kw', {}),
                "validators": [v.__class__.__name__ for v in getattr(field, 'validators', [])]
            }
        })

        if provider and provider.is_azure:
            # For Azure providers, deployment_name is required
            if not field.data:
                logger.error("Missing required deployment_name for Azure provider", extra={
                    "field_state": {
                        "value": field.data,
                        "required": getattr(field, 'flags', {}).required,
                        "render_kw": getattr(field, 'render_kw', {})
                    }
                })
                raise ValidationError("Deployment name is required for Azure OpenAI providers.")

            # Validate pattern if one exists
            pattern = self.provider_validation_rules.get('model_id')
            if pattern:
                import re
                if not re.match(pattern, field.data):
                    logger.error("Invalid deployment_name format", extra={
                        "value": field.data,
                        "pattern": pattern
                    })
                    raise ValidationError("Deployment name does not match the required format specified by the provider.")
                logger.debug("Deployment name pattern validation passed", extra={
                    "value": field.data,
                    "pattern": pattern
                })
        else:
            # For non-Azure providers, deployment_name should be empty
            if field.data:
                logger.warning("Deployment name provided for non-Azure provider", extra={
                    "value": field.data,
                    "provider": provider.name if provider else None
                })
            field.data = ""  # Clear the field for non-Azure providers
            return

    def validate_version(self, field):
        """Optimistic concurrency control"""
        if self.is_edit and self._obj:
            current_version = Model.get_by_id(self._obj.id).version
            if int(field.data) != current_version:
                raise ValidationError("This model was modified by another user. Please refresh.")

# ------------------------------------------------------------------------
# DefaultModelForm
# ------------------------------------------------------------------------

class DefaultModelForm(FlaskForm):
    """
    Form for editing the default model configuration during registration if it is invalid,
    specifically designed for o1-preview model configuration.
    """
    provider_id = SelectField(
        "Provider",
        validators=[DataRequired(message="Provider is required.")],
        coerce=int,
        render_kw={"readonly": True, "disabled": True},
    )
    name = StringField(
        "Model Name",
        validators=[
            DataRequired(message="Model name is required."),
            Length(max=50, message="Model name cannot exceed 50 characters."),
            Regexp(
                r"^[a-zA-Z0-9_\-\s]+$",
                message="Model name can only contain letters, numbers, spaces, underscores, and hyphens.",
            ),
        ],
        default="o1-preview",
    )
    deployment_name = StringField(
        "Deployment Name",
        validators=[
            DataRequired(message="Deployment name is required."),
            Length(max=50, message="Deployment name cannot exceed 50 characters."),
            Regexp(
                r"^[a-zA-Z0-9_\-\s]+$",
                message="Deployment name can only contain letters, numbers, spaces, underscores, and hyphens.",
            ),
        ]
    )
