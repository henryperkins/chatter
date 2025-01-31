"""
Email utility functions for sending emails using SMTP.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template
from typing import Any, List, Union
from email.utils import formataddr
import ssl

logger = logging.getLogger(__name__)


def create_email_message(
    to: Union[str, List[str]], subject: str, template: str, **template_params: Any
) -> MIMEMultipart:
    """
    Create an email message using a template.

    Args:
        to: Recipient email address or list of addresses
        subject: Email subject
        template: Template file path (relative to templates directory)
        **template_params: Parameters to pass to the template

    Returns:
        MIMEMultipart: Prepared email message object
    """
    # Create message container
    msg = MIMEMultipart("alternative")

    # Get sender from config
    sender_name = current_app.config.get("MAIL_SENDER_NAME", "Azure Chat App")
    sender_email = current_app.config["MAIL_USERNAME"]

    msg["From"] = formataddr((sender_name, sender_email))
    msg["Subject"] = subject

    # Handle multiple recipients
    if isinstance(to, list):
        msg["To"] = ", ".join(to)
    else:
        msg["To"] = to

    try:
        # Render HTML template
        html = render_template(template, **template_params)

        # Attach HTML version
        msg.attach(MIMEText(html, "html"))

        return msg

    except Exception as e:
        logger.error(f"Error creating email message: {str(e)}")
        raise


def send_email(
    to: Union[str, List[str]], subject: str, template: str, **template_params: Any
) -> bool:
    """
    Send an email using SMTP.

    Args:
        to: Recipient email address or list of addresses
        subject: Email subject
        template: Template file path (relative to templates directory)
        **template_params: Parameters to pass to the template

    Returns:
        bool: True if email was sent successfully, False otherwise

    Raises:
        SMTPException: If there is an error sending the email
        RuntimeError: If mail settings are not configured
    """
    if not current_app.config.get("MAIL_SERVER"):
        raise RuntimeError("Mail server not configured")

    try:
        msg = create_email_message(to, subject, template, **template_params)

        # Create secure SSL/TLS context
        context = ssl.create_default_context()

        # Connect to SMTP server
        with smtplib.SMTP(
            current_app.config["MAIL_SERVER"], current_app.config["MAIL_PORT"]
        ) as server:
            if current_app.config["MAIL_USE_TLS"]:
                server.starttls(context=context)

            if (
                current_app.config["MAIL_USERNAME"]
                and current_app.config["MAIL_PASSWORD"]
            ):
                server.login(
                    current_app.config["MAIL_USERNAME"],
                    current_app.config["MAIL_PASSWORD"],
                )

            # Send email
            server.send_message(msg)

            logger.info(
                f"Email sent successfully to {msg['To']}",
                extra={
                    "subject": subject,
                    "template": template,
                    "recipient": msg["To"],
                },
            )
            return True

    except Exception as e:
        logger.error(
            f"Failed to send email: {str(e)}",
            extra={"to": to, "subject": subject, "template": template},
            exc_info=True,
        )
        raise


def send_test_email(to: str) -> bool:
    """
    Send a test email to verify email configuration.

    Args:
        to: Test recipient email address

    Returns:
        bool: True if test email was sent successfully
    """
    try:
        send_email(
            to=to,
            subject="Test Email",
            template="emails/test_email.html",
            test_param="This is a test email to verify the email configuration.",
        )
        return True
    except Exception as e:
        logger.error(f"Test email failed: {str(e)}")
        return False
