import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.config import Config

logger = logging.getLogger(__name__)


def send_email(subject: str, recipient_email: str, text_content: str, html_content: str) -> None:
    """Send an email with the specified subject and content.
    
    Args:
        subject: Email subject line
        recipient_email: Recipient's email address
        text_content: Plain text email content
        html_content: HTML formatted email content
        
    Raises:
        Exception: If email sending fails
    """
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = Config.EMAIL_SENDER
    message["To"] = recipient_email

    message.attach(MIMEText(text_content, "plain"))
    message.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.sendmail(Config.EMAIL_SENDER, recipient_email, message.as_string())
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise Exception(f"Failed to send email: {e}")


def send_reset_email(recipient_email: str, reset_link: str) -> None:
    """Send a password reset email to the specified recipient.
    
    Args:
        recipient_email: Recipient's email address
        reset_link: Password reset URL
    """
    subject = "Password Reset Request"
    text = f"Please click the following link to reset your password: {reset_link}"
    html = f"<html><body><p>{text}</p><a href='{reset_link}'>{reset_link}</a></body></html>"
    send_email(subject, recipient_email, text, html)


def send_verification_email(recipient_email: str, verification_token: str) -> None:
    """Send an email to the user with a verification link.
    
    Args:
        recipient_email: Recipient's email address
        verification_token: Email verification token
    """
    verification_url = f"{Config.APP_URL}/auth/verify_email/{verification_token}"
    subject = "Email Verification"
    text = f"Please click the following link to verify your email: {verification_url}"
    html = f"<html><body><p>{text}</p><a href='{verification_url}'>{verification_url}</a></body></html>"
    send_email(subject, recipient_email, text, html)