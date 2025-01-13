from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    FloatField,
    IntegerField,
    BooleanField,
    TextAreaField,
    SelectField,
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
    ValidationError,
)
from wtforms.widgets import TextInput
import re
from typing import Any
from database import db_session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

class StrippedStringField(StringField):
    """Custom StringField that strips leading/trailing whitespace."""

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = valuelist[0].strip()

class URLFieldWithPlaceholder(URLField):
    widget = TextInput()

    def __init__(self, label=None, validators=None, placeholder=None, **kwargs):
        super(URLFieldWithPlaceholder, self).__init__(label, validators, **kwargs)
        self.widget.input_type = "url"
        self.placeholder = placeholder

    def __call__(self, **kwargs):
        if self.placeholder:
            kwargs.setdefault("placeholder", self.placeholder)
        return super(URLFieldWithPlaceholder, self).__call__(**kwargs)

class LoginForm(FlaskForm):
    """
    Form for user login.
    """

    username = StrippedStringField(
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

    username = StrippedStringField(
        "Username",
        validators=[
            DataRequired(message="Username is required."),
            Length(
                min=4, max=20, message="Username must be between 4 and 20 characters."
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
        try:
            with db_session() as session:
                if session.execute(
                    text("SELECT username FROM users WHERE LOWER(username) = LOWER(:username)"),
                    {"username": field.data.lower()},
                ).fetchone():
                    raise ValidationError("This username is already taken.")
        except SQLAlchemyError as e:
            logger.error(f"Database error during username validation: {e}")
            raise ValidationError("An error occurred while validating the username.")

    def validate_email(self, field: Any) -> None:
        """
        Custom validator for email.
        """
        try:
            with db_session() as session:
                if session.execute(
                    text("SELECT email FROM users WHERE LOWER(email) = LOWER(:email)"),
                    {"email": field.data.lower()},
                ).fetchone():
                    raise ValidationError("This email is already registered.")
        except SQLAlchemyError as e:
            logger.error(f"Database error during email validation: {e}")
            raise ValidationError("An error occurred while validating the email.")

    def validate_password(self, field: Any) -> None:
        """
        Validate password strength and security requirements.
        """
        validate_password_strength(field.data)

class ModelForm(FlaskForm):
    """
    Form for creating or updating AI model configurations.
    """

    name = StrippedStringField(
        "Model Name",
        validators=[
            DataRequired(message="Model name is required."),
            Length(max=50, message="Model name cannot exceed 50 characters."),
            # Updated regular expression to disallow spaces
            Regexp(
                r"^[a-zA-Z0-9_\-]+$",
                message="Model name can only contain letters, numbers, underscores, and hyphens.",
            ),
        ],
    )
    deployment_name = StrippedStringField(
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
    api_endpoint = URLFieldWithPlaceholder(
        "API Endpoint",
        validators=[
            DataRequired(message="API endpoint is required."),
            URL(message="Must be a valid URL."),
            Regexp(
                r"^https://[^/]+\.openai\.azure\.com/?$",
                message="Must be a valid Azure OpenAI endpoint URL.",
            ),
        ],
        placeholder="https://your-endpoint.openai.azure.com/",
    )
    api_key = StringField(
        "API Key",
        validators=[
            DataRequired(message="API key is required."),
            Length(min=32, message="API key must be at least 32 characters long."),
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
            field.data = 1.0
        elif field.data is not None and not (0 <= field.data <= 2):
            raise ValidationError("Temperature must be between 0 and 2.")

    def validate_max_tokens(self, field: Any) -> None:
        """
        Validate max_tokens based on whether special handling is required.
        """
        if self.requires_o1_handling.data:
            field.data = None
        elif field.data is not None and field.data <= 0:
            raise ValidationError("Max tokens must be a positive integer.")

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
            field.data = value
        except (TypeError, ValueError) as e:
            raise ValidationError(
                "Max completion tokens must be a valid integer."
            ) from e

    def validate_requires_o1_handling(self, field: Any) -> None:
        """
        Additional validation when special handling is required.
        """
        if field.data:
            self.temperature.data = None
            self.max_tokens.data = None

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
    if len(password) < 12:  # Increased minimum length
        raise ValidationError("Password must be at least 12 characters long.")

    # Check for required character types
    if not any(c.isupper() for c in password):
        raise ValidationError("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        raise ValidationError("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        raise ValidationError("Password must contain at least one number.")
    if not any(c in "!@#$%^&*(),.?\":{}|<>" for c in password):
        raise ValidationError(
            'Password must contain at least one special character (!@#$%^&*(),.?":{}|<>).'
        )

    # Check for common passwords
    with open("common_passwords.txt", "r") as file:
        common_passwords = {line.strip().lower() for line in file}

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
            forward_seq = seq[i : i + 3]
            backward_seq = forward_seq[::-1]
            if forward_seq in password or backward_seq in password:
                raise ValidationError("Password cannot contain sequential characters.")

    # Check for repeated characters
    for i in range(len(password) - 2):
        if password[i] == password[i + 1] == password[i + 2]:
            raise ValidationError(
                "Password must not contain three or more repeated characters in a row."
            )