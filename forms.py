from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    EqualTo,
    Regexp,
    ValidationError,
)
import re
from database import get_db  # Import to access the database in validation methods


class StrongPassword(object):
    def __init__(self, message=None):
        if not message:
            message = "Password must be at least 8 characters long and include uppercase, lowercase, number, and special character."
        self.message = message

    def __call__(self, form, field):
        password = field.data
        if (
            len(password) < 8
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"\d", password)
            or not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)
        ):
            raise ValidationError(self.message)


class LoginForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=20),
            Regexp(
                r"^\w+$",
                message="Username must contain only letters, numbers, or underscores.",
            ),
        ],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=20),
            Regexp(
                r"^\w+$",
                message="Username must contain only letters, numbers, or underscores.",
            ),
        ],
    )
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), StrongPassword()])
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )

    def validate_username(self, field):
        username = field.data.strip()
        db = get_db()
        existing_user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing_user:
            raise ValidationError("Username already exists. Please choose a different username.")

    def validate_email(self, field):
        email = field.data.strip()
        db = get_db()
        existing_user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing_user:
            raise ValidationError("Email already registered. Please use a different email.")