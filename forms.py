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
from azure_config import validate_api_endpoint
from database import db_connection


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
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=6),
        ],
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
        validators=[DataRequired(), NumberRange(min=1, max=1000)],
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
    def validate_api_endpoint(self, field):
        api_key = os.getenv("AZURE_OPENAI_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        deployment_name = self.deployment_name.data

        if not api_key:
            raise ValidationError(
                "Azure OpenAI API key is not found in environment variables."
            )

        try:
            if not validate_api_endpoint(
                field.data, api_key, deployment_name, api_version
            ):
                raise ValidationError("Invalid or unreachable Azure OpenAI endpoint.")
        except ValueError as ex:
            raise ValidationError(str(ex))

    def validate_temperature(self, field):
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

    def validate_max_tokens(self, field):
        if self.requires_o1_handling.data:
            if field.data is not None:
                raise ValidationError(
                    "Max tokens must not be set for models requiring o1-preview handling."
                )
        else:
            if field.data is not None and field.data <= 0:
                raise ValidationError("Max tokens must be a positive integer.")

    def validate_max_completion_tokens(self, field):
        if field.data is None or field.data <= 0:
            raise ValidationError("Max completion tokens must be a positive integer.")
        if self.requires_o1_handling.data and field.data is None:
            raise ValidationError(
                "Max completion tokens must be specified for o1-preview models."
            )

    def validate_api_version(self, field):
        if self.requires_o1_handling.data and field.data != "2024-12-01-preview":
            raise ValidationError(
                "API Version must be '2024-12-01-preview' for o1-preview models."
            )

class ResetPasswordForm(FlaskForm):
    """
    Form for resetting user password.
    """
    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=6),
        ],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Reset Password")
