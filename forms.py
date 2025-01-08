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

    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


class RegistrationForm(FlaskForm):
    """
    Form for user registration.
    """

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=4, max=20),
            Regexp(
                r"^[a-zA-Z0-9_]+$",
                message="Username can only contain letters, numbers, and underscores.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(),
            Regexp(
                r"^[^@]+@(?!.*\.(xyz|top|work|party|gq|cf|ml|ga|tk|cn)).*$",
                message="Please use a valid non-disposable email address."
            )
        ]
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired()],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Register")


class ModelForm(FlaskForm):
    """
    Form for creating or updating AI model configurations.
    """

    name = StringField(
        "Model Name",
        validators=[
            DataRequired(),
            Length(max=50),
            Regexp(
                r"^[a-zA-Z0-9_\-\s]+$",
                message="Model name can only contain letters, numbers, spaces, underscores, and hyphens.",
            ),
        ],
    )
    deployment_name = StringField(
        "Deployment Name",
        validators=[
            DataRequired(),
            Length(max=50),
            Regexp(
                r"^[a-zA-Z0-9_\-]+$",
                message="Deployment name can only contain letters, numbers, underscores, and hyphens.",
            ),
        ],
    )
    description = TextAreaField(
        "Description (Optional)",
        validators=[Optional(), Length(max=500)],
    )
    api_endpoint = URLField(
        "API Endpoint",
        validators=[
            DataRequired(),
            URL(message="Must be a valid URL."),
            Regexp(
                r"^https://.*\.openai\.azure\.com/.*$",
                message="Must be a valid Azure OpenAI endpoint URL.",
            ),
        ],
    )
    api_key = StringField(
        "API Key",
        validators=[
            DataRequired(),
            Length(min=32, message="API key must be at least 32 characters long"),
            Regexp(
                r"^[a-zA-Z0-9]+$",
                message="API key can only contain letters and numbers",
            ),
        ],
    )
    temperature = FloatField(
        "Temperature (Creativity Level)",
        validators=[
            Optional(),  # Make field optional
            NumberRange(min=0, max=2),
        ],
    )
    max_tokens = IntegerField(
        "Max Tokens (Input)",
        validators=[
            Optional(),  # Make field optional
            NumberRange(min=1, max=4000),
        ],
    )
    max_completion_tokens = IntegerField(
        "Max Completion Tokens (Output)",
        validators=[DataRequired(), NumberRange(min=1, max=32000)],
        default=500,
    )
    model_type = SelectField(
        "Model Type",
        choices=[("azure", "Azure"), ("o1-preview", "o1-preview")],
        validators=[DataRequired()],
        default="azure",
    )
    api_version = StringField(
        "API Version",
        validators=[DataRequired(), Length(max=20)],
        default="2024-12-01-preview",
    )
    requires_o1_handling = BooleanField("Special Handling for o1-preview Models")
    is_default = BooleanField("Set as Default Model")

    # ----- Custom Validators -----
    def validate_username(self, field: Any) -> None:
        # Convert to lowercase for case-insensitive comparison
        username = field.data.lower().strip()
        if len(username) < 4:
            raise ValidationError("Username must be at least 4 characters long.")
        if username != field.data.strip():
            raise ValidationError("Username cannot contain leading or trailing spaces.")

        # Check for common username patterns that might be confusing
        from database import db_connection
        with db_connection() as db:
            existing = db.execute(
                "SELECT username FROM users WHERE LOWER(username) = ?",
                (username,)
            ).fetchone()
            if existing:
                raise ValidationError("This username is already taken.")

    def validate_email(self, field: Any) -> None:
        email = field.data.lower().strip()
        if email != field.data:
            raise ValidationError("Email cannot contain leading or trailing spaces.")

        from database import db_connection
        with db_connection() as db:
            existing = db.execute(
                "SELECT email FROM users WHERE LOWER(email) = ?",
                (email,)
            ).fetchone()
            if existing:
                raise ValidationError("This email is already registered.")

    def validate_password(self, field: Any) -> None:
        """Validate password strength and security requirements."""
        validate_password_strength(field.data)

    def validate_temperature(self, field: Any) -> None:
        if self.requires_o1_handling.data:
            if field.data is not None:
                raise ValidationError(
                    "Temperature must not be set for models requiring o1-preview handling."
                )
        else:
            if field.data is None:
                raise ValidationError("Temperature is required.")
            elif not (0 <= field.data <= 2):
                raise ValidationError("Temperature must be between 0 and 2.")

    def validate_max_tokens(self, field: Any) -> None:
        if self.requires_o1_handling.data:
            if field.data is not None:
                raise ValidationError(
                    "Max tokens must not be set for models requiring o1-preview handling."
                )
        else:
            if field.data is not None and field.data <= 0:
                raise ValidationError("Max tokens must be a positive integer.")

    def validate_max_completion_tokens(self, field: Any) -> None:
        if field.data is None or field.data <= 0:
            raise ValidationError("Max completion tokens must be a positive integer.")
        if self.requires_o1_handling.data and field.data is None:
            raise ValidationError(
                "Max completion tokens must be specified for o1-preview models."
            )

    def validate_api_version(self, field: Any) -> None:
        if self.requires_o1_handling.data and field.data != "2024-12-01-preview":
            raise ValidationError(
                "API Version must be '2024-12-01-preview' for o1-preview models."
            )


def validate_password_strength(password: str) -> None:
    """Validate password meets security requirements."""
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
        # Letters
        'abcdefghijklmnopqrstuvwxyz',
        # Numbers
        '01234567890',
        # Keyboard rows
        'qwertyuiop',
        'asdfghjkl',
        'zxcvbnm'
    )

    for sequence in sequences:
        # Check forward and backward sequences of 3 or more characters
        for i in range(len(sequence) - 2):
            forward = sequence[i:i + 3]
            backward = sequence[i:i + 3][::-1]
            if forward in password.lower() or backward in password.lower():
                raise ValidationError(
                    "Password contains sequential characters. Please avoid using sequential letters or numbers."
                )

    # Check for repeated characters
    for i in range(len(password) - 2):
        if password[i] == password[i + 1] == password[i + 2]:  # Add spaces around +
            raise ValidationError("Password cannot contain three or more repeated characters in a row.")


class ResetPasswordForm(FlaskForm):
    """Form for resetting user password."""
    password = PasswordField(
        "New Password",
        validators=[DataRequired()],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Reset Password")

    def validate_password(self, field: Any) -> None:
        """Validate password strength and security requirements."""
        validate_password_strength(field.data)
