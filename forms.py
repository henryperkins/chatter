import re
import logging
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

from database import db_session, db_transaction, is_initialized

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------
# Custom Fields: NullableIntegerField, NullableFloatField
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
    """

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
            raise ValidationError("Username is required")

        username = field.data.strip()

        if not is_initialized():
            logger.warning("Database not initialized - skipping username validation")
            return

        try:
            with db_transaction() as db:
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
    )

    requires_authentication = BooleanField("Requires Authentication", default=True)


# ------------------------------------------------------------------------
# ModelForm
# ------------------------------------------------------------------------


class ModelForm(FlaskForm):
    """
    Form for creating or updating AI model configurations.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Check for encryption key before form validation
        from config import Config

        if not getattr(Config, "ENCRYPTION_KEY", None):
            logger.warning("ENCRYPTION_KEY environment variable not set")

        # Load providers for the select field
        with db_session() as session:
            providers = session.execute(
                text("SELECT id, name FROM providers ORDER BY name")
            ).fetchall()
            self.provider_id.choices = [(p.id, p.name) for p in providers]

    provider_id = SelectField(
        "Provider",
        validators=[DataRequired(message="Provider is required.")],
        coerce=int,
        description="Select the provider for this model",
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
    )
    deployment_name = StringField(
        "Deployment Name",
        validators=[
            DataRequired(message="Deployment name is required."),
            Length(max=50, message="Deployment name cannot exceed 50 characters."),
            Regexp(
                r"^[a-zA-Z0-9_\-]+$",
                message="Deployment name can only contain letters, numbers, underscores, and hyphens.",
            ),
        ],
    )
    description = TextAreaField(
        "Description (Optional)",
        validators=[
            Optional(),
            Length(max=500, message="Description cannot exceed 500 characters."),
        ],
    )
    api_endpoint = URLField(
        "API Endpoint",
        validators=[
            DataRequired(message="API endpoint is required."),
            URL(message="Must be a valid URL."),
        ],
    )
    api_key = StringField(
        "API Key",
        validators=[
            DataRequired(message="API key is required."),
            Length(min=32, message="API key must be at least 32 characters long."),
        ],
    )

    temperature = NullableFloatField(
        "Temperature (Creativity Level)",
        validators=[
            Optional(),
            NumberRange(min=0, max=2, message="Temperature must be between 0 and 2."),
        ],
    )
    max_tokens = NullableIntegerField(
        "Max Tokens (Input)",
        validators=[Optional()],
        default=None,
        render_kw={"placeholder": "Leave blank for no limit"},
    )
    max_completion_tokens = NullableIntegerField(
        "Max Completion Tokens (Output)",
        validators=[
            DataRequired(message="Max completion tokens is required."),
            NumberRange(min=1, max=16384, message="Must be between 1 and 16384."),
        ],
    )

    model_type = SelectField(
        "Model Type",
        choices=[("azure", "Azure"), ("o1-preview", "o1-preview")],
        validators=[DataRequired(message="Model type is required.")],
        default="azure",
    )
    api_version = StringField(
        "API Version",
        validators=[
            DataRequired(message="API version is required."),
            Length(max=20, message="API version cannot exceed 20 characters."),
        ],
        default="2024-12-01-preview",
    )
    requires_o1_handling = BooleanField("Special Handling for o1-preview Models")
    supports_streaming = BooleanField("Enable Response Streaming")
    is_default = BooleanField("Set as Default Model")

    # ------------------------ Custom Validators --------------------------

    def validate_api_endpoint(self, field: Any) -> None:
        """
        Remove trailing slashes in the submitted URL
        """
        field.data = field.data.rstrip("/")

    def validate_max_completion_tokens(self, field: Any) -> None:
        """Ensure max_completion_tokens is valid and within range."""
        try:
            value = int(field.data) if field.data not in (None, '', 'None') else 0

            # Base validation for all models
            base_validation = (1 <= value <= 16384)
            if not base_validation:
                raise ValidationError("Max completion tokens must be between 1 and 16384")

            # o1-preview model validation
            if self.requires_o1_handling.data and value > 8300:
                raise ValidationError("Max completion tokens must be between 1 and 8300 for o1-preview models")

            field.data = value

        except (TypeError, ValueError):
            raise ValidationError("Max completion tokens must be a valid integer")

    def validate_provider_id(self, field: Any) -> None:
        """
        Validate that the chosen provider exists in the database.
        """
        with db_session() as session:
            provider = session.execute(
                text("SELECT id FROM providers WHERE id = :id"),
                {"id": field.data},
            ).scalar()
            if not provider:
                raise ValidationError("Invalid provider selected")

    def validate_temperature(self, field: Any) -> None:
        """
        Validate temperature based on whether special handling is required.
        """
        if field.data in ("", None, "None"):
            field.data = None
            return

        try:
            temp = float(field.data)
            if self.requires_o1_handling.data:
                if temp != 1.0:
                    raise ValidationError(
                        "For o1 models, temperature must be exactly 1.0."
                    )
                field.data = 1.0
            elif not (0 <= temp <= 2):
                raise ValidationError("Temperature must be between 0 and 2.")
            field.data = temp
        except (ValueError, TypeError):
            raise ValidationError("Temperature must be a valid number between 0 and 2.")

    def validate_max_tokens(self, field: Any) -> None:
        """
        Validate max_tokens based on whether special handling is required.
        """
        if self.requires_o1_handling.data:
            # Automatically set max_tokens to None for o1-preview
            field.data = None
        elif field.data is not None:
            try:
                value = int(field.data)
                if not (1 <= value <= 4000):
                    raise ValidationError("Max tokens must be between 1 and 4000.")
                field.data = value
            except (TypeError, ValueError):
                raise ValidationError(
                    "Max tokens must be a valid integer between 1 and 4000."
                )

    def validate_requires_o1_handling(self, field: Any) -> None:
        """
        Additional validation logic when special handling is required.
        """
        if field.data:
            # For o1-preview, we override certain fields
            self.temperature.data = 1.0
            self.max_tokens.data = None
            self.supports_streaming.data = False
            self.max_completion_tokens.data = 8300


# ------------------------------------------------------------------------
# DefaultModelForm
# ------------------------------------------------------------------------


class DefaultModelForm(FlaskForm):
    """
    Form for editing the default model configuration during registration if it is invalid,
    specifically designed for o1-preview model configuration.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Check for encryption key before form validation
        from config import Config

        if not getattr(Config, "ENCRYPTION_KEY", None):
            logger.warning("ENCRYPTION_KEY environment variable not set")

        # Set default temperature if None
        if self.temperature.data is None:
            self.temperature.data = 1.0

        # Attempt to load or create the default Azure provider
        try:
            with db_session() as db:
                provider = db.execute(
                    text(
                        """
                        SELECT id
                        FROM providers
                        WHERE name = 'Azure OpenAI' OR slug = 'azure-openai'
                        LIMIT 1
                        """
                    )
                ).scalar()
                if provider:
                    self.provider_id.data = provider
                else:
                    # Create Azure provider if not found
                    from models.provider import Provider

                    provider_id = Provider.create(
                        {
                            "name": "Azure OpenAI",
                            "slug": "azure-openai",
                            "api_base_url": Config.DEFAULT_API_ENDPOINT,
                            "capabilities": {
                                "supports_streaming": True,
                                "max_tokens": Config.DEFAULT_MAX_TOKENS,
                            },
                            "requires_authentication": True,
                        }
                    )
                    self.provider_id.data = provider_id
        except Exception as e:
            logger.error("Error setting up provider: %s", str(e))
            # Default to 1 if database operations fail
            self.provider_id.data = 1

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
                r"^[a-zA-Z0-9_\-]+$",
                message="Deployment name can only contain letters, numbers, underscores, and hyphens.",
            ),
        ],
        default="o1-preview",
    )
    description = TextAreaField(
        "Description",
        validators=[
            Optional(),
            Length(max=500, message="Description cannot exceed 500 characters."),
        ],
        default="Azure OpenAI o1-preview model",
    )
    api_endpoint = URLField(
        "API Endpoint",
        validators=[
            DataRequired(message="API endpoint is required."),
            URL(message="Must be a valid URL."),
            Regexp(
                r"^https://[^/]+\.openai\.azure\.com/?$",
                message="Must be a valid Azure OpenAI endpoint URL.",
            ),
        ],
        default="https://openai-hp.openai.azure.com/",
    )
    api_key = StringField(
        "API Key",
        validators=[
            DataRequired(message="API key is required."),
            Length(min=32, message="API key must be at least 32 characters long."),
        ],
        default="9SPmgaBZ0tlnQrdRU0IxLsanKHZiEUMD2RASDEUhOchf6gyqRLWCJQQJ99BAACHYHv6XJ3w3AAABACOGKt5l",
    )
    temperature = NullableFloatField(
        "Temperature",
        validators=[Optional()],
        default=1.0,
        render_kw={"readonly": True},
    )
    max_tokens = NullableIntegerField(
        "Max Tokens",
        validators=[Optional()],
        default=None,
        render_kw={"readonly": True, "disabled": True},
    )
    max_completion_tokens = NullableIntegerField(
        "Max Completion Tokens",
        validators=[
            DataRequired(message="Max completion tokens is required."),
            NumberRange(
                min=1, max=8300, message="Must be between 1 and 8300 for o1-preview."
            ),
        ],
        default=8300,
    )
    requires_o1_handling = BooleanField(
        "Requires o1-preview Handling",
        default=True,
        render_kw={"readonly": True, "checked": True, "disabled": True},
    )
    supports_streaming = BooleanField(
        "Supports Streaming",
        default=False,
        render_kw={"readonly": True, "disabled": True},
    )
    api_version = StringField(
        "API Version",
        validators=[
            DataRequired(message="API version is required."),
            Length(max=20, message="API version cannot exceed 20 characters."),
            Regexp(
                r"^\d{4}-\d{2}-\d{2}-preview$",
                message="API version must be in format YYYY-MM-DD-preview",
            ),
        ],
        default="2024-12-01-preview",
        render_kw={"readonly": True},
    )
    model_type = StringField(
        "Model Type",
        validators=[DataRequired(message="Model type is required.")],
        default="o1-preview",
        render_kw={"type": "hidden"},
    )
    submit = SubmitField("Save Configuration")

    # ------------------------ Custom Validators --------------------------

    def validate_api_endpoint(self, field: Any) -> None:
        """
        Remove trailing slashes in the submitted URL.
        """
        field.data = field.data.rstrip("/")

    def validate_temperature(self, field: Any) -> None:
        """
        Ensure temperature is exactly 1.0 for o1-preview.
        """
        if field.data is None:
            field.data = 1.0
        elif field.data != 1.0:
            raise ValidationError("Temperature must be exactly 1.0 for o1-preview.")

    def validate_max_completion_tokens(self, field: Any) -> None:
        """
        Ensure max_completion_tokens is within o1-preview limits.
        """
        try:
            value = int(field.data)
            if not (1 <= value <= 8300):
                raise ValidationError(
                    "Max completion tokens must be between 1 and 8300 for o1-preview."
                )
            field.data = value
        except (TypeError, ValueError) as e:
            raise ValidationError(
                "Max completion tokens must be a valid integer."
            ) from e


# ------------------------------------------------------------------------
# Password Strength Utility
# ------------------------------------------------------------------------


def validate_password_strength(password: str) -> None:
    """
    Validate password meets security requirements:
      1. Minimum 8 characters
      2. Includes uppercase, lowercase, digit, special char
      3. Not in a common password list
      4. Not containing sequential or repeated characters
    """
    if not password:
        raise ValidationError("Password is required.")

    password = password.strip()
    errors = []

    # Check length
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")

    # Required character types
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one number.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        errors.append("Password must contain at least one special character.")

    if errors:
        raise ValidationError(" ".join(errors))

    # Common password check
    common_passwords = {
        "password",
        "password123",
        "123456",
        "qwerty",
        "abc123",
        "12345678",
        "letmein",
    }
    if password.lower() in common_passwords:
        raise ValidationError(
            "This password is too common. Please choose a stronger password."
        )

    # Check for sequential characters
    sequences = (
        "abcdefghijklmnopqrstuvwxyz",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "01234567890",
        "qwertyuiop",
        "asdfghjkl",
        "zxcvbnm",
    )
    for seq in sequences:
        seq_len = len(seq)
        for i in range(seq_len - 2):
            forward_seq = seq[i: i + 3]
            backward_seq = forward_seq[::-1]
            if forward_seq in password or backward_seq in password:
                raise ValidationError("Password cannot contain sequential characters.")

    # Check for repeated characters
    for i in range(len(password) - 2):
        if password[i] == password[i + 1] == password[i + 2]:
            raise ValidationError(
                "Password must not contain three or more repeated characters in a row."
            )


# ------------------------------------------------------------------------
# ResetPasswordForm
# ------------------------------------------------------------------------


class ResetPasswordForm(FlaskForm):
    """
    Form for resetting a user's password.
    """

    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(message="Password is required."),
            Length(min=8, message="Password must be at least 8 characters long."),
            Regexp(
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).+$",
                message="Must include uppercase, lowercase, digit, and special character.",
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Reset Password")
