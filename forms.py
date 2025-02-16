import re
import logging
from datetime import datetime, timedelta
from models.user import User

from flask import current_app, request
from flask_wtf import FlaskForm
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
from sqlalchemy import text

from database import db_session, is_initialized
from chat_utils import validate_password_strength
from utils.encryption import encrypt_api_key, EncryptionError
from models.provider import Provider
from models.model import Model

# Azure libraries for deployment validation (optional)
try:
    AZURE_IMPORTS_AVAILABLE = True
except ImportError:
    AZURE_IMPORTS_AVAILABLE = False

# Cryptography imports for key derivation
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Optional: Input sanitization if using a web application firewall
# from waf import sanitize_input

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------------------

def validate_azure_deployment(self, deployment_name: str, subscription_id: str, resource_group: str, account_name: str) -> bool:
    """
    Validate that the specified Azure deployment exists.
    """
    if not AZURE_IMPORTS_AVAILABLE:
        logger.warning("Azure SDK not installed - skipping deployment validation")
        return True
        
    try:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
        
        credential = DefaultAzureCredential()
        client = CognitiveServicesManagementClient(
            credential=credential,
            subscription_id=subscription_id
        )
        deployments = client.deployments.list(
            resource_group_name=resource_group,
            account_name=account_name,
            deployment_name=deployment_name
        )
        deployments = client.deployments.list(resource_group, account_name)
        return any(d.name == deployment_name for d in deployments)
    except Exception as e:
        logger.error(f"Error validating Azure deployment: {str(e)}", exc_info=True)
        return False

def derive_encryption_key(master_key: bytes, salt: bytes) -> bytes:
    """
    Derive an encryption key using PBKDF2HMAC.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=32,
        salt=salt,
        iterations=600000,
    )
    return kdf.derive(master_key)

def verify_database_schema():
    """
    Verify that the required database schema is in place.
    (Implementation depends on your DB/ORM; ensure migrations are applied.)
    """
    # required_schema = {
    #     'users': ['locked_until', 'version'],
    #     'models': ['deployment_name', 'azure_verified']
    # }
    logger.info("Database schema verification is pending. Please ensure migrations are applied.")


# ------------------------------------------------------------------------
# Custom Fields: NullableIntegerField, NullableFloatField, (Optional) HardenedStringField
# ------------------------------------------------------------------------

class NullableIntegerField(IntegerField):
    """
    A custom IntegerField that treats empty or invalid input as None.
    """
    def process_formdata(self, valuelist):
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

# Optional: HardenedStringField for input sanitization
# class HardenedStringField(StringField):
#     def process_formdata(self, valuelist):
#         if valuelist:
#             self.data = sanitize_input(valuelist[0])

# ------------------------------------------------------------------------
# LoginForm
# ------------------------------------------------------------------------

class LoginForm(FlaskForm):
    """
    Form for user login.
    """
    username = StringField(
        "Username",
        validators=[DataRequired(message="Username is required.")],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password is required.")],
    )
    remember = BooleanField("Remember Me", default=False)
    submit = SubmitField("Login")

    def validate_username(self, field: Field) -> None:
        """
        Add account lockout checks, password spray protection, and security logging.
        """
        username = field.data.strip().lower()
        ip_address = request.remote_addr

        try:
            with db_session() as db:
                # 1) Check if account is locked
                account_locked_until = db.execute(
                    text("""
                        SELECT account_locked_until
                        FROM users
                        WHERE username = :username
                    """),
                    {"username": username}
                ).scalar()

                if account_locked_until is not None and account_locked_until > datetime.utcnow():
                    logger.error("Account locked", extra={
                        'username': username,
                        'ip': ip_address,
                        'locked_until': account_locked_until
                    })
                    raise ValidationError("Account temporarily locked - please try again later.")

                # 2) Check recent failed attempts for username or IP
                recent_failures = db.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM login_attempts
                        WHERE (username = :username OR ip_address = :ip)
                        AND success = false
                        AND attempted_at > NOW() - INTERVAL '15 minutes'
                    """),
                    {"username": username, "ip": ip_address}
                ).scalar() or 0  # Handle NULL case

                if recent_failures and recent_failures >= 5:
                    extra_failures = recent_failures - 5
                    lock_minutes = 15 * (2 ** min(extra_failures, 5))  # exponential backoff
                    lock_time = datetime.utcnow() + timedelta(minutes=lock_minutes)
                    db.execute(
                        text("""
                            UPDATE users
                            SET locked_until = :lock_time
                            WHERE username = :username
                        """),
                        {"lock_time": lock_time, "username": username}
                    )
                    logger.error("Excessive login failures", extra={
                        'username': username,
                        'ip': ip_address,
                        'recent_failures': recent_failures,
                        'lock_time': lock_time
                    })
                    raise ValidationError(f"Too many failed attempts - account locked for {lock_minutes} minutes.")

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Security validation error: {str(e)}", exc_info=True)
            raise ValidationError("Login temporarily unavailable - please try again later.")

# ------------------------------------------------------------------------
# RegistrationForm
# ------------------------------------------------------------------------

class RegistrationForm(FlaskForm):
    """
    Form for user registration.
    Inherits CSRF protection from FlaskForm.
    """
    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Username is required."),
            Length(min=4, max=20, message="Username must be between 4 and 20 characters."),
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
            Length(min=12, message="Password must be at least 12 characters long."),
            Regexp(
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]).{12,}$",
                message=(
                    "Password must contain at least 12 characters including: "
                    "1 uppercase, 1 lowercase, 1 number, and 1 special character"
                ),
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
        Checks if username is already taken and performs format checks.
        """
        if not field.data:
            return
            
        username = field.data.strip()
        
        # Validacion basica del formato primero
        if len(username) < 4:
            raise ValidationError("Username must be at least 4 characters long.")
            
        if not re.match(r"^[a-zA-Z0-9_]+$", username):
            raise ValidationError("Username can only contain letters, numbers, and underscores.")
            
        if field.data != username:
            raise ValidationError("Username cannot contain leading or trailing spaces.")

        # Verificar si el username ya existe usando el modelo User
        try:
            with db_session() as session:
                if User.get_by_username(session, username):
                    raise ValidationError("This username is already taken. Please choose a different username.")
        except Exception as e:
            logger.error(f"Error validating username: {str(e)}", exc_info=True)
            raise ValidationError("An error occurred while checking username availability. Please try again later.")

    def validate_email(self, field: Field) -> None:
        """
        Custom validator for email. Checks if the email is already registered.
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

        except ValidationError:
            raise
        except Exception as e:
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
        except ValidationError as ve:
            raise ve
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
            URL(message="Must be a valid URL."),
        ],
        description="Base URL for your OpenAI-compatible API (e.g., https://api.openai.com/v1)",
    )

    requires_authentication = BooleanField("Requires Authentication", default=True)

    endpoint_pattern = StringField(
        "API Path",
        validators=[
            DataRequired(message="API path is required."),
            Length(max=255, message="API path cannot exceed 255 characters."),
            Regexp(r"^/.*$", message="API path must start with /"),
        ],
        default="/chat/completions",
        description="API path appended to the base URL (defaults to /chat/completions).",
    )

    def validate_endpoint_pattern(self, field):
        """Validate the API path format."""
        try:
            if self.slug and self.slug.data and "azure" in self.slug.data.lower():
                raise ValidationError("Azure OpenAI endpoints should be configured via Azure provider type.")
            if not field.data.startswith("/"):
                raise ValidationError("API path must start with /")
            if "//" in field.data:
                raise ValidationError("API path cannot contain double slashes")
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Error validating API path: {str(e)}")

    def validate_api_base_url(self, field):
        """Validate the API base URL."""
        try:
            if field.data and "azure" in str(field.data).lower():
                raise ValidationError("Azure OpenAI endpoints should be configured through the Azure provider type.")
            if field.data:
                field.data = str(field.data).rstrip("/")
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
                message="Must be YYYY-MM-DD or YYYY-MM-DD-preview",
            ),
        ],
        default="2024-12-01-preview",
    )

    api_key = PasswordField(
        "API Key",
        validators=[
            Optional(),
            Length(min=32, message="API key must be at least 32 characters if provided."),
        ],
        description="Provider-level API key (if using a shared key)",
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
        description="Default model name for this provider",
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
        description="Default deployment name (Azure OpenAI only)",
    )

    is_azure = BooleanField(
        "Azure OpenAI Provider",
        default=False,
        description="Check if this is an Azure OpenAI provider",
    )

# ------------------------------------------------------------------------
# ModelForm
# ------------------------------------------------------------------------

class ModelForm(FlaskForm):
    name = StringField('Model Name', validators=[DataRequired(), Length(max=255)])
    deployment_name = StringField(
        'Deployment Name',
        validators=[Optional(), Length(max=255)],
        description="Required for Azure OpenAI providers; leave empty for others."
    )
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    provider_id = SelectField('Provider', coerce=int, validators=[DataRequired()])
    api_key = PasswordField(
        'API Key',
        validators=[DataRequired(), Length(min=32, message="API key must be at least 32 characters.")]
    )
    model_type = SelectField(
        'Model Type',
        choices=[
            ('azure', 'Azure OpenAI (Standard)'),
            ('o1', 'Azure OpenAI (o1)'),
            ('o1-mini', 'Azure OpenAI (o1-mini)'),
            ('o1-preview', 'Azure OpenAI (o1-preview)'),
            ('o3-mini', 'Azure OpenAI (o3-mini)'),
        ],
        validators=[DataRequired()],
        description="Select the model type - o1/o3 models support advanced reasoning capabilities"
    )
    reasoning_effort = SelectField(
        'Reasoning Effort',
        choices=[
            ('low', 'Low - Faster responses, fewer tokens'),
            ('medium', 'Medium - Balanced speed and reasoning (Default)'),
            ('high', 'High - More thorough reasoning, more tokens'),
        ],
        default='medium',
        validators=[Optional()],
        description="Controls how many reasoning tokens the model generates before responding"
    )
    store = BooleanField(
        'Store Completion',
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
    api_version = StringField(
        'API Version',
        validators=[
            DataRequired(message="API version is required."),
            Length(max=20, message="API version cannot exceed 20 characters."),
            Regexp(
                r"^\d{4}-\d{2}-\d{2}(?:-preview)?$",
                message="API version must be in format YYYY-MM-DD or YYYY-MM-DD-preview"
            )
        ],
        default="2024-12-01-preview"
    )
    version = HiddenField('Version')
    api_endpoint = URLField(
        'API Endpoint',
        validators=[DataRequired(message="API endpoint is required."), URL(message="Must be a valid URL.")],
    )

    def __init__(self, *args, **kwargs):
        self.is_edit = kwargs.pop('is_edit', False)
        self._obj = kwargs.pop('obj', None)  # The Model object if editing
        self.provider_validation_rules = {}
        super().__init__(*args, **kwargs)

        logger.debug("Initializing ModelForm", extra={
            "is_edit": self.is_edit,
            "has_data": bool(args and args[0])
        })

        self.setup_edit_mode()
        self.load_providers()
        self.load_provider_validation_rules()

        provider = None
        if self.provider_id.data:
            provider = Provider.get_by_id(self.provider_id.data)
            logger.debug("Found provider", extra={
                "provider_id": self.provider_id.data,
                "provider_name": provider.name if provider else None,
                "is_azure": provider.is_azure if provider else None
            })

        self.setup_deployment_name_field(provider)

        logger.debug("Form initialized", extra={
            "deployment_name_state": {
                "value": self.deployment_name.data if hasattr(self, 'deployment_name') else None,
                "required": getattr(self.deployment_name, 'flags', {}).required if hasattr(self.deployment_name, 'flags') else None,
                "render_kw": getattr(self.deployment_name, 'render_kw', {}) if hasattr(self.deployment_name, 'render_kw') else None
            }
        })

        for field in ['requires_o1_handling', 'supports_streaming', 'is_default']:
            if field not in self.data:
                setattr(self, field, False)

    def load_provider_validation_rules(self):
        provider_id = self.provider_id.data
        logger.debug("Loading provider validation rules", extra={"provider_id": provider_id})

        if not provider_id:
            self.provider_validation_rules = {}
            return

        provider = Provider.get_by_id(provider_id)
        if provider is None:
            logger.warning("Provider not found", extra={"provider_id": provider_id})
            self.provider_validation_rules = {}
            return

        try:
            rules = provider.validation_rules
            if isinstance(rules, str):
                import json
                rules = json.loads(rules)
            logger.debug("Loaded provider validation rules", extra={
                "provider": provider.name,
                "rules": rules
            })
        except Exception:
            logger.error("Error loading validation rules", exc_info=True)
            rules = {}

        if provider.is_azure:
            logger.debug("Setting up Azure provider validation")
            self.deployment_name.validators = [DataRequired(), Length(max=255)]
            if hasattr(self.deployment_name, 'flags'):
                self.deployment_name.flags.required = True
            if not hasattr(self.deployment_name, 'render_kw'):
                self.deployment_name.render_kw = {}
            self.deployment_name.render_kw['required'] = 'required'
            self.deployment_name.render_kw['aria-required'] = 'true'
        else:
            logger.debug("Setting up non-Azure provider validation")
            self.deployment_name.validators = [Optional(), Length(max=255)]
            if hasattr(self.deployment_name, 'flags'):
                self.deployment_name.flags.required = False
            if not hasattr(self.deployment_name, 'render_kw'):
                self.deployment_name.render_kw = {}
            self.deployment_name.render_kw.pop('required', None)
            self.deployment_name.render_kw.pop('aria-required', None)

        self.provider_validation_rules = rules

    def setup_edit_mode(self):
        """
        Modify form behavior for edit mode: make API key optional if editing.
        """
        if self.is_edit:
            self.api_key.validators = [
                Optional(),
                Length(min=32, message="API key must be at least 32 characters if provided.")
            ]
            self.api_key.description = "Leave blank to keep existing key"
            self.api_key.flags.required = False

    def load_providers(self):
        """
        Populate provider_id choices from the database.
        """
        try:
            with db_session() as session:
                providers = session.execute(
                    text("SELECT id, name FROM providers ORDER BY name")
                ).mappings().fetchall()
                self.provider_id.choices = [(p['id'], p['name']) for p in providers]
        except Exception as e:
            logger.error(f"Error loading providers: {str(e)}")
            self.provider_id.choices = []

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
            self.deployment_name.render_kw.update({'tabindex': '-1'})
            self.deployment_name.render_kw.pop('required', None)
            self.deployment_name.render_kw.pop('aria-required', None)

    def validate_deployment_name(self, field):
        """
        Enhanced validation for deployment_name with Azure deployment check.
        """
        provider = Provider.get_by_id(self.provider_id.data) if self.provider_id.data else None

        if provider and provider.is_azure:
            if not field.data:
                raise ValidationError("Deployment name is required for Azure OpenAI providers.")

            pattern = self.provider_validation_rules.get('model_id')
            if pattern and not re.match(pattern, field.data):
                raise ValidationError("Deployment name does not match provider format requirements.")

            subscription_id = current_app.config.get('AZURE_SUBSCRIPTION_ID')
            resource_group = current_app.config.get('AZURE_RESOURCE_GROUP')
            account_name = current_app.config.get('AZURE_ACCOUNT_NAME')
            if not validate_azure_deployment(field.data, subscription_id, resource_group, account_name):
                raise ValidationError("Azure deployment not found.")
        else:
            if field.data:
                raise ValidationError("Deployment names are only allowed for Azure providers.")

    def validate_max_completion_tokens(self, field):
        """
        Enhanced validation with provider constraints.
        """
        try:
            value = int(field.data)
        except (TypeError, ValueError):
            raise ValidationError("Must be a valid integer")

        provider = Provider.get_by_id(self.provider_id.data)
        if provider and isinstance(provider.capabilities, dict):
            provider_max = provider.capabilities.get('max_tokens', 16384)
        else:
            provider_max = 16384

        if self.requires_o1_handling.data:
            if not (1 <= value <= 32768):
                raise ValidationError("Must be between 1-32768 for o1-preview models (OpenAI recommended).")
        else:
            if not (1 <= value <= provider_max):
                raise ValidationError(f"Must be between 1-{provider_max} for this provider.")

    def validate_temperature(self, field):
        """
        Temperature validation with o1-preview constraint.
        """
        if self.requires_o1_handling.data:
            raise ValidationError("Temperature is fixed for o1-preview models; please do not specify a value.")
        if field.data is None:
            return
        try:
            temp = float(field.data)
            if not (0 <= temp <= 2):
                raise ValidationError("Must be between 0.0 and 2.0")
        except ValueError:
            raise ValidationError("Must be a valid number")

    def validate_supports_streaming(self, field):
        """
        Streaming validation with o1-preview constraint.
        """
        if self.requires_o1_handling.data and field.data:
            raise ValidationError("Streaming not supported for o1-preview models.")

    def process_api_key(self):
        """
        Handle API key encryption with improved security and error handling.
        """
        try:
            if self.is_edit and not self.api_key.data:
                # Clear API key field to avoid exposing the stored encrypted key.
                self.api_key.data = None
                return

            if self.api_key.data:
                if len(self.api_key.data) < 32:
                    raise ValidationError("API key must be at least 32 characters.")

                from config import Config
                config_instance = Config()
                encryption_key = config_instance.ENCRYPTION_KEY
                if not encryption_key:
                    logger.critical("Encryption key missing in configuration.")
                    raise ValidationError("System configuration error - please contact administrator.")

                self.api_key.data = encrypt_api_key(self.api_key.data, encryption_key)
        except EncryptionError as e:
            logger.error(f"API key encryption failed: {str(e)}")
            raise ValidationError("Failed to secure API key - please try again.")
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing API key: {str(e)}")
            raise ValidationError("Error processing credentials - please try again.")

    def validate_api_endpoint(self, field):
        if not field.data:
            return

        pattern = self.provider_validation_rules.get('endpoint')
        if pattern:
            if not re.match(pattern, field.data):
                raise ValidationError(
                    "API endpoint does not match the required format specified by the provider."
                )

    def validate_version(self, field):
        """
        Optimistic concurrency control.
        """
        if self.is_edit and self._obj and hasattr(self._obj, 'id') and field.data:
            model = Model.get_by_id(self._obj.id)
            if model and hasattr(model, 'version') and int(field.data) != model.version:
                raise ValidationError("This model was modified by another user. Please refresh.")

# ------------------------------------------------------------------------
# DefaultModelForm
# ------------------------------------------------------------------------

class DefaultModelForm(FlaskForm):
    """
    Form for editing the default model configuration during registration if invalid,
    specifically for o1-preview model configuration.
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
        ],
    )
    submit = SubmitField("Save Default Model")
