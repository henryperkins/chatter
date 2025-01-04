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
from azure_config import validate_api_endpoint  # Import the correct function
from database import db_connection  # Use the centralized context manager


# ----- MODEL FORM -----
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
        validators=[DataRequired(), NumberRange(min=0, max=2)],
        default=1.0,
    )
    max_tokens = IntegerField(
        "Max Tokens (Input)",
        validators=[Optional(), NumberRange(min=1, max=4000)],
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
        default="2024-10-01-preview",
    )
    requires_o1_handling = BooleanField("Special Handling for o1-preview Models")
    is_default = BooleanField("Set as Default Model")

    # ----- Custom Validators -----
    def validate_api_endpoint(self, field):
        """
        Validate the API endpoint structure and connectivity.
        """
        api_key = os.getenv("AZURE_OPENAI_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        deployment_name = self.deployment_name.data  # Retrieve deployment name from the form

        if not api_key:
            raise ValidationError("Azure OpenAI API key is not found in environment variables.")

        try:
            if not validate_api_endpoint(field.data, api_key, deployment_name, api_version):
                raise ValidationError("Invalid or unreachable Azure OpenAI endpoint.")
        except ValueError as ex:
            raise ValidationError(str(ex))

    def validate_max_completion_tokens(self, field):
        """
        Validate max_completion_tokens for models that require o1 handling.
        """
        if self.requires_o1_handling.data and not field.data:
            raise ValidationError(
                "max_completion_tokens must be specified for o1-preview models."
            )

    def validate_api_version(self, field):
        """
        Validate the API version for models like o1-preview.
        """
        if self.requires_o1_handling.data and field.data != "2024-12-01-preview":
            raise ValidationError("API Version must be '2024-12-01-preview' for o1-preview models.")


# ----- USER REGISTRATION FORM -----
class RegistrationForm(FlaskForm):
    """
    Form for new user registration.
    """

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=20),
            Regexp(
                r"^[a-zA-Z0-9_]+$",
                message="Username must contain only letters, numbers, and underscores.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(message="Must be a valid email address."),
            Length(max=120),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=8, message="Password must be at least 8 characters long."),
            Regexp(
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])(?=.*[\W_]).+$",
                message=(
                    "Password must contain at least an uppercase letter, a lowercase "
                    "letter, a number, and a special character."
                ),
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )

    # --- Custom Validators for Unique Username and Email ---
    def validate_username(self, field):
        with db_connection() as db:
            user = db.execute("SELECT id FROM users WHERE username = ?", (field.data,)).fetchone()
            if user:
                raise ValidationError("Username already exists. Please choose a different username.")

    def validate_email(self, field):
        with db_connection() as db:
            user = db.execute("SELECT id FROM users WHERE email = ?", (field.data,)).fetchone()
            if user:
                raise ValidationError("A user with this email address already exists.")


# ----- USER LOGIN FORM -----
class LoginForm(FlaskForm):
    """
    Form for user login.
    """

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=20),
            Regexp(
                r"^[a-zA-Z0-9_]+$",
                message="Username must contain only letters, numbers, and underscores.",
            ),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired()],
    )


# ----- ADDITIONAL FORMS (OPTIONAL) -----

class PasswordResetForm(FlaskForm):
    """
    Optional form for resetting passwords, if required later.
    """
    email = StringField(
        "Email Address",
        validators=[
            DataRequired(),
            Email(),
        ],
    )
    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=8),
            Regexp(
                r"^(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])(?=.*[\W_]).+$",
                message="Password must include upper and lower case, digits, and special characters.",
            ),
        ],
    )
    confirm_new_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="Passwords must match."),
        ],
    )