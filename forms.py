import re
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
from typing import Any
from database import get_db
from sqlalchemy import text

# Custom Fields to handle None values in IntegerField and FloatField
class NullableIntegerField(IntegerField):
    def process_formdata(self, valuelist):
        if valuelist and valuelist[0]:
            try:
                self.data = int(valuelist[0])
            except (ValueError, TypeError):
                self.data = None
        else:
            self.data = None

class NullableFloatField(FloatField):
    def process_formdata(self, valuelist):
        if valuelist and valuelist[0]:
            try:
                self.data = float(valuelist[0])
            except (ValueError, TypeError):
                self.data = None
        else:
            self.data = None

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
            Length(min=4, max=20, message="Username must be between 4 and 20 characters."),
            Regexp(r"^[a-zA-Z0-9_]+$", message="Username can only contain letters, numbers, and underscores."),
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
            Length(min=8, message="Password must be at least 8 characters long."),
            Regexp(
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).+$",
                message="Password must include at least one uppercase letter, one lowercase letter, one number, and one special character.",
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

    def validate_username(self, field: Any) -> None:
        """
        Custom validator for username.
        """
        username = field.data.strip()
        
        # Check for spaces
        if field.data != username:
            raise ValidationError("Username cannot contain leading or trailing spaces.")
            
        # Check length
        if len(username) < 4:
            raise ValidationError("Username must be at least 4 characters long.")
            
        # Check format
        if not re.match(r"^[a-zA-Z0-9_]+$", username):
            raise ValidationError("Username can only contain letters, numbers, and underscores.")

        # Check uniqueness
        with get_db() as db:
            if db.execute(
                text("SELECT id FROM users WHERE LOWER(username) = LOWER(:username)"),
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

    temperature = NullableFloatField(
        "Temperature (Creativity Level)",
        validators=[
            Optional(),
            NumberRange(min=0, max=2, message="Temperature must be between 0 and 2."),
        ],
    )
    max_tokens = NullableIntegerField(
        "Max Tokens (Input)",
        validators=[
            Optional(),  # Removed NumberRange validator
        ],
        default=None,
        render_kw={"placeholder": "Leave blank for no limit"}
    )
    max_completion_tokens = NullableIntegerField(
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
    version = NullableIntegerField(
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
        if field.data in ('', None, 'None'):
            field.data = None
            return
            
        try:
            temp = float(field.data)
            if self.requires_o1_handling.data:
                if temp != 1.0:
                    raise ValidationError("For o1 models, temperature must be exactly 1.0.")
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
            # When requires_o1_handling is True, automatically set max_tokens to None
            field.data = None
        elif field.data is not None:
            try:
                value = int(field.data)
                if not (1 <= value <= 4000):
                    raise ValidationError("Max tokens must be between 1 and 4000.")
                field.data = value  # Ensure the value is an integer
            except (TypeError, ValueError):
                raise ValidationError("Max tokens must be a valid integer between 1 and 4000.")

    def validate_requires_o1_handling(self, field: Any) -> None:
        """
        Additional validation when special handling is required.
        """
        if field.data:
            # When requires_o1_handling is True, automatically set temperature and max_tokens to None
            # and disable streaming support
            self.temperature.data = 1.0
            self.max_tokens.data = None
            self.supports_streaming.data = False
            self.max_completion_tokens.data = 8300


class DefaultModelForm(FlaskForm):
    """
    Form for editing the default model configuration during registration if it is invalid.
    Specifically designed for o1-preview model configuration.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Check for encryption key before form validation
        from config import Config
        if not Config.ENCRYPTION_KEY:
            raise ValueError("ENCRYPTION_KEY environment variable must be set")
        # Ensure temperature is set to 1.0
        if self.temperature.data is None:
            self.temperature.data = 1.0

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
        default="o1-preview"
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
        default="o1-preview"
    )
    description = TextAreaField(
        "Description",
        validators=[
            Optional(),
            Length(max=500, message="Description cannot exceed 500 characters."),
        ],
        default="Azure OpenAI o1-preview model"
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
        default="https://openai-hp.openai.azure.com/"
    )
    api_key = StringField(
        "API Key",
        validators=[
            DataRequired(message="API key is required."),
            Length(min=32, message="API key must be at least 32 characters long."),
        ],
        default="9SPmgaBZ0tlnQrdRU0IxLsanKHZiEUMD2RASDEUhOchf6gyqRLWCJQQJ99BAACHYHv6XJ3w3AAABACOGKt5l"
    )
    temperature = NullableFloatField(
        "Temperature",
        validators=[Optional()],  # Change from DataRequired to Optional
        default=1.0,
        render_kw={"readonly": True}
    )
    max_tokens = NullableIntegerField(
        "Max Tokens",
        validators=[Optional()],
        default=None,
        render_kw={"readonly": True, "disabled": True}
    )
    max_completion_tokens = NullableIntegerField(
        "Max Completion Tokens",
        validators=[
            DataRequired(message="Max completion tokens is required."),
            NumberRange(min=1, max=8300, message="Max completion tokens must be between 1 and 8300 for o1-preview."),
        ],
        default=8300
    )
    requires_o1_handling = BooleanField(
        "Requires o1-preview Handling",
        default=True,
        render_kw={"readonly": True, "checked": True, "disabled": True}
    )
    supports_streaming = BooleanField(
        "Supports Streaming",
        default=False,
        render_kw={"readonly": True, "disabled": True}
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
        render_kw={"readonly": True}
    )
    model_type = StringField(
        "Model Type",
        validators=[DataRequired(message="Model type is required.")],
        default="o1-preview",
        render_kw={"type": "hidden"}
    )
    submit = SubmitField("Save Configuration")

    def validate_api_endpoint(self, field: Any) -> None:
        """
        Custom validator for API endpoint.
        """
        # Remove any trailing slashes
        field.data = field.data.rstrip("/")

    def validate_temperature(self, field: Any) -> None:
        """
        Ensure temperature is exactly 1.0 for o1-preview or None
        """
        if field.data is None:
            field.data = 1.0  # Set to 1.0 if None
        elif field.data != 1.0:
            raise ValidationError("Temperature must be exactly 1.0 for o1-preview.")

    def validate_max_completion_tokens(self, field: Any) -> None:
        """
        Ensure max_completion_tokens is within o1-preview limits.
        """
        try:
            value = int(field.data)
            if not (1 <= value <= 8300):
                raise ValidationError("Max completion tokens must be between 1 and 8300 for o1-preview.")
            field.data = value
        except (TypeError, ValueError) as e:
            raise ValidationError("Max completion tokens must be a valid integer.") from e


def validate_password_strength(password: str) -> None:
    """
    Validate password meets security requirements.
    """
    if not password:
        raise ValidationError("Password is required.")

    password = password.strip()
    errors = []
    
    # Check minimum length
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    
    # Check for required character types
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
    
    # Additional validations
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
