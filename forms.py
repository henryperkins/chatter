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
    ValidationError,
)
from models import Model
import re
from database import get_db  # Import to access the database in validation methods


class ModelForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[
            DataRequired(),
            Length(max=50),
            Regexp(
                r"^[\w\s\-]+$",
                message="Name can only contain letters, numbers, spaces, underscores, and hyphens.",
            ),
        ],
    )
    deployment_name = StringField(
        "Deployment Name",
        validators=[
            DataRequired(),
            Length(max=50),
            Regexp(
                r"^[\w\-]+$",
                message="Deployment name can only contain letters, numbers, underscores, and hyphens.",
            ),
        ],
    )
    description = TextAreaField(
        "Description",
        validators=[Optional(), Length(max=500)],
    )
    api_endpoint = URLField(
        "API Endpoint",
        validators=[
            DataRequired(),
            URL(),
            Regexp(
                r'^https://.*\.openai\.azure\.com/.*$',
                message="Must be a valid Azure OpenAI endpoint URL"
            )
        ]
    )
    temperature = FloatField(
        "Temperature",
        validators=[DataRequired(), NumberRange(min=0, max=2)],
        default=1.0,
    )
    max_tokens = IntegerField(
        "Max Tokens",
        validators=[Optional(), NumberRange(min=1, max=4000)],
    )
    max_completion_tokens = IntegerField(
        "Max Completion Tokens",
        validators=[DataRequired(), NumberRange(min=1, max=1000)],
        default=500,
    )
    model_type = SelectField(
        "Model Type",
        choices=[("azure", "Azure"), ("openai", "OpenAI")],
        validators=[DataRequired()],
        default="azure",
    )
    api_version = StringField(
        "API Version",
        validators=[DataRequired()],
        default="2024-10-01-preview",
    )
    requires_o1_handling = BooleanField("Requires o1 Handling")
    is_default = BooleanField("Set as Default Model")

    def validate_api_endpoint(self, field):
        """Validate the API endpoint."""
        api_key = os.getenv("AZURE_OPENAI_KEY")
        if not api_key:
            raise ValidationError("Azure OpenAI API key not found in environment variables")

        try:
            if not Model.validate_api_endpoint(field.data, api_key):
                raise ValidationError("Invalid API endpoint")
        except ValueError as e:
            raise ValidationError(str(e))


class StrongPassword:
    """Custom validator for password strength."""

    def __init__(self, message=None):
        self.message = (
            message
            or "Password must contain at least 8 characters, uppercase, lowercase, number and special character"
        )

    def __call__(self, form, field):
        password = field.data
        if not (
            len(password) >= 8
            and any(c.isupper() for c in password)
            and any(c.islower() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in '!@#$%^&*(),.?":{}|<>' for c in password)
        ):
            raise ValidationError(self.message)


class LoginForm(FlaskForm):
    """Form for user login."""

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=20),
            Regexp(
                r"^[\w]+$",
                message="Username must contain only letters, numbers, and underscores",
            ),
        ],
    )
    password = PasswordField("Password", validators=[DataRequired()])


class RegistrationForm(FlaskForm):
    """Form for user registration."""

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=20),
            Regexp(
                r"^[\w]+$",
                message="Username must contain only letters, numbers, and underscores",
            ),
        ],
    )
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), StrongPassword()])
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )

    def validate_username(self, field):
        db = get_db()
        if db.execute(
            "SELECT id FROM users WHERE username = ?", (field.data,)
        ).fetchone():
            raise ValidationError("Username already exists")

    def validate_email(self, field):
        db = get_db()
        if db.execute("SELECT id FROM users WHERE email = ?", (field.data,)).fetchone():
            raise ValidationError("Email already registered")
