import os
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
from azure_config import validate_api_endpoint


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
        username = field.data.lower().strip()
        if len(username) < 4:
            raise ValidationError("Username must be at least 4 characters long.")
        if username != field.data.strip():
            raise ValidationError("Username cannot contain leading or trailing spaces.")

        # Check for existing username
        from database import db_connection
        with db_connection() as db:
            existing = db.execute(
                "SELECT username FROM users WHERE LOWER(username) = ?",
                (username,)
            ).fetchone()
            if existing:
                raise ValidationError("This username is already taken.")

    def validate_email(self, field: Any) -> None:
        """
        Custom validator for email.
        """
        email = field.data.lower().strip()
        if email != field.data:
            raise ValidationError("Email cannot contain leading or trailing spaces.")

        # Check for existing email
        from database import db_connection
        with db_connection() as db:
            existing = db.execute(
                "SELECT email FROM users WHERE LOWER(email) = ?",
                (email,)
            ).fetchone()
            if existing:
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
        validators=[Optional(), Length(max=500, message="Description cannot exceed 500 characters.")],
    )
    api_endpoint = URLField(
        "API Endpoint",
        validators=[
            DataRequired(message="API endpoint is required."),
            URL(message="Must be a valid URL."),
            Regexp(
                r"^https://.*\.openai\.azure\.com/.*$",
                message="Must be a valid Azure OpenAI endpoint URL.",
            ),
        ],
    )
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
            NumberRange(min=1, max=4000, message="Max tokens must be between 1 and 4000."),
        ],
    )
    max_completion_tokens = IntegerField(
        "Max Completion Tokens (Output)",
        validators=[
            DataRequired(message="Max completion tokens is required."),
            NumberRange(min=1, max=1000, message="Max completion tokens must be between 1 and 1000."),
        ],
        default=500,
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
    is_default = BooleanField("Set as Default Model")

    def validate_api_endpoint(self, field: Any) -> None:
        """
        Custom validator for API endpoint.
        """
        api_key = os.getenv("AZURE_OPENAI_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        deployment_name = str(self.deployment_name.data)

        if not api_key:
            raise ValidationError("Azure OpenAI API key is not found in environment variables.")

        try:
            if not validate_api_endpoint(
                str(field.data), api_key, deployment_name, api_version
            ):
                raise ValidationError("Invalid or unreachable Azure OpenAI endpoint.")
        except ValueError as ex:
            raise ValidationError(str(ex))


class ResetPasswordForm(FlaskForm):
    """
    Form for resetting user password.
    """

    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(message="New password is required."),
        ],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(message="Please confirm your new password."),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Reset Password")

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
    if not any(c in "!@#$%^&*(),.?\":{}|<>" for c in password):
        raise ValidationError("Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>).")

    # Check for common passwords
    common_passwords = {
        'password', 'password123', '123456', 'qwerty', 'letmein', 'admin123',
        'welcome', 'monkey', 'dragon', 'baseball', 'football', 'master'
    }
    if password.lower() in common_passwords:
        raise ValidationError("This password is too common. Please choose a stronger password.")

    # Check for sequential characters
    sequences = (
        'abcdefghijklmnopqrstuvwxyz',
        '01234567890',
        'qwertyuiop',
        'asdfghjkl',
        'zxcvbnm'
    )

    for sequence in sequences:
        for i in range(len(sequence) - 2):
            forward = sequence[i:i + 3]
            backward = sequence[i:i + 3][::-1]
            if forward in password.lower() or backward in password.lower():
                raise ValidationError("Password contains sequential characters. Please avoid using sequential letters or numbers.")

    # Check for repeated characters
    for i in range(len(password) - 2):
        if password[i] == password[i + 1] == password[i + 2]:
            raise ValidationError("Password cannot contain three or more repeated characters in a row.")