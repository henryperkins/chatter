from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    FloatField,
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
import os
from typing import Any
from database import get_db
from sqlalchemy import text


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
    submit = SubmitField("Login")


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
            Regexp(
                r"^[^@]+@(?!.*\.(xyz|top|work|party|gq|cf|ml|ga|tk|cn)).*$",
                message="Please use a valid non-disposable email address.",
            ),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
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

    def validate_username(self, field: Any) -> None:
        """
        Custom validator for username.
        """
        # First check for spaces
        if field.data != field.data.strip():
            raise ValidationError("Username cannot contain leading or trailing spaces.")
            
        # Then check length of cleaned username
        username = field.data.strip().lower()
        if len(username) < 4:
            raise ValidationError("Username must be at least 4 characters long.")

        # Check for existing username using text()
        with get_db() as db:
            if db.execute(
                text("SELECT username FROM users WHERE LOWER(username) = :username"),
                {"username": username},
            ).fetchone():
                raise ValidationError("This username is already taken.")

    def validate_email(self, field: Any) -> None:
        """
        Custom validator for email.
        """
        email = field.data.lower().strip()
        if email != field.data:
            raise ValidationError("Email cannot contain leading or trailing spaces.")

        # Check for existing email using text()
        with get_db() as db:
            if db.execute(
                text("SELECT email FROM users WHERE LOWER(email) = :email"),
                {"email": email},
            ).fetchone():
                raise ValidationError("This email is already registered.")

    def validate_password(self, field: Any) -> None:
        """
        Validate password strength and security requirements.
        """
        validate_password_strength(field.data)


class ModelForm(FlaskForm):
    """
    Form for creating or updating AI model configurations.
    """

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
            Regexp(
                r"^https://[^/]+\.openai\.azure\.com/?$",
                message="Must be a valid Azure OpenAI endpoint URL.",
            ),
        ],
    )

    api_key = StringField(
        "API Key",
        validators=[
            DataRequired(message="API key is required."),
            Length(min=32, message="API key must be at least 32 characters long."),
        ],
    )

    def validate_api_endpoint(self, field: Any) -> None:
        """
        Custom validator for API endpoint.
        """
        # Remove any trailing slashes
        field.data = field.data.rstrip("/")

    temperature = FloatField(
        "Temperature (Creativity Level)",
        validators=[
            Optional(),
            NumberRange(min=0, max=2, message="Temperature must be between 0 and 2."),
        ],
    )
    max_tokens = IntegerField(
        "Max Tokens (Input)",
        validators=[
            Optional(),
            NumberRange(
                min=1, max=4000, message="Max tokens must be between 1 and 4000."
            ),
        ],
    )
    max_completion_tokens = IntegerField(
        "Max Completion Tokens (Output)",
        validators=[
            DataRequired(message="Max completion tokens is required."),
            NumberRange(
                min=1,
                max=16384,
                message="Max completion tokens must be between 1 and 16384.",
            ),
        ],
    )

    def validate_max_completion_tokens(self, field: Any) -> None:
        """
        Custom validator for max_completion_tokens.
        """
        try:
            value = int(field.data)
            if not (1 <= value <= 16384):
                raise ValidationError(
                    "Max completion tokens must be between 1 and 16384."
                )
            field.data = value  # Ensure the value is an integer
        except (TypeError, ValueError) as e:
            raise ValidationError(
                "Max completion tokens must be a valid integer."
            ) from e

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
    version = IntegerField(
        "Version",
        default=1,
        render_kw={"type": "hidden"},  # Make it a hidden field
        validators=[
            DataRequired(message="Version is required."),
            NumberRange(min=1, message="Version must be a positive integer."),
        ],
    )

    def validate_temperature(self, field: Any) -> None:
        """
        Validate temperature based on whether special handling is required.
        """
        if self.requires_o1_handling.data:
            # When requires_o1_handling is True, set temperature to 1 as required by o1-preview models
            field.data = 1.0
        elif field.data is not None and not (0 <= field.data <= 2):
            raise ValidationError("Temperature must be between 0 and 2.")

    def validate_max_tokens(self, field: Any) -> None:
        """
        Validate max_tokens based on whether special handling is required.
        """
        if self.requires_o1_handling.data:
            # When requires_o1_handling is True, automatically set max_tokens to None
            field.data = None
        elif field.data is not None and field.data <= 0:
            raise ValidationError("Max tokens must be a positive integer.")
def validate_requires_o1_handling(self, field: Any) -> None:
    """
    Additional validation when special handling is required.
    """
    if field.data:
        # When requires_o1_handling is True, automatically set temperature and max_tokens to None
        # and disable streaming support
        self.temperature.data = None
        self.max_tokens.data = None
        self.supports_streaming.data = False


class DefaultModelForm(FlaskForm):
    """
    Form for editing the default model configuration during registration if it is invalid.
    """
    name = StringField(
        "Model Name",
        validators=[
            DataRequired(message="Model name is required."),
            Length(max=50, message="Model name cannot exceed 50 characters."),
        ],
        default=os.getenv("DEFAULT_MODEL_NAME", "GPT-4")
    )
    deployment_name = StringField(
        "Deployment Name",
        validators=[
            DataRequired(message="Deployment name is required."),
            Length(max=50, message="Deployment name cannot exceed 50 characters."),
        ],
        default=os.getenv("DEFAULT_DEPLOYMENT_NAME", "gpt-4")
    )
    description = TextAreaField(
        "Description",
        validators=[
            Optional(),
            Length(max=500, message="Description cannot exceed 500 characters."),
        ],
        default=os.getenv("DEFAULT_MODEL_DESCRIPTION", "Default GPT-4 model")
    )
    api_endpoint = URLField(
        "API Endpoint",
        validators=[
            DataRequired(message="API endpoint is required."),
            URL(message="Must be a valid URL."),
        ],
        default=os.getenv("DEFAULT_API_ENDPOINT", "https://your-resource.openai.azure.com")
    )
    api_key = StringField(
        "API Key",
        validators=[
            DataRequired(message="API key is required."),
            Length(min=32, message="API key must be at least 32 characters long."),
        ],
        default=os.getenv("AZURE_API_KEY", "your_default_api_key")
    )
    temperature = FloatField(
        "Temperature",
        validators=[
            Optional(),
            NumberRange(min=0, max=2, message="Temperature must be between 0 and 2."),
        ],
        default=os.getenv("DEFAULT_TEMPERATURE", "1.0")
    )
    max_tokens = IntegerField(
        "Max Tokens",
        validators=[
            Optional(),
            NumberRange(min=1, max=4000, message="Max tokens must be between 1 and 4000."),
        ],
        default=os.getenv("DEFAULT_MAX_TOKENS", "4000")
    )
    max_completion_tokens = IntegerField(
        "Max Completion Tokens",
        validators=[
            DataRequired(message="Max completion tokens is required."),
            NumberRange(min=1, max=16384, message="Max completion tokens must be between 1 and 16384."),
        ],
        default=os.getenv("DEFAULT_MAX_COMPLETION_TOKENS", "500")
    )
    requires_o1_handling = BooleanField(
        "Requires o1-preview Handling",
        default=os.getenv("DEFAULT_REQUIRES_O1_HANDLING", "False").lower() == "true"
    )
    supports_streaming = BooleanField(
        "Supports Streaming",
        default=os.getenv("DEFAULT_SUPPORTS_STREAMING", "True").lower() == "true"
    )
    api_version = StringField(
        "API Version",
        validators=[
            DataRequired(message="API version is required."),
            Length(max=20, message="API version cannot exceed 20 characters."),
        ],
        default=os.getenv("AZURE_API_VERSION", "2024-12-01-preview")
    )
    submit = SubmitField("Save Configuration")

    def validate_password(self, field: Any) -> None:
        """
        Validate password strength and security requirements.
        """
        validate_password_strength(field.data)


def validate_password_strength(password: str) -> None:
    """
    Validate password meets security requirements.
    """
    if not password:
        raise ValidationError("Password is required.")

    password = password.strip()
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")

    # Check for required character types
    if not any(c.isupper() for c in password):
        raise ValidationError("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        raise ValidationError("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        raise ValidationError("Password must contain at least one number.")
    if all(c not in '!@#$%^&*(),.?":{}|<>' for c in password):
        raise ValidationError(
            'Password must contain at least one special character (!@#$%^&*(),.?":{}|<>).'
        )

    # Check for common passwords
    common_passwords = {
        "password", "password123", "123456", "qwerty", "abc123", "12345678", "letmein"
    }
    if password.lower() in common_passwords:
        raise ValidationError("This password is too common. Please choose a stronger password.")

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
            forward_seq = seq[i:i + 3]
            backward_seq = forward_seq[::-1]
            if forward_seq in password or backward_seq in password:
                raise ValidationError("Password cannot contain sequential characters.")
    # Check for repeated characters
    for i in range(len(password) - 2):
        if password[i] == password[i + 1] == password[i + 2]:
            raise ValidationError(
                "Password must not contain three or more repeated characters in a row."
            )
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
                message="Password must include at least one uppercase letter, one lowercase letter, one number, and one special character.",
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
