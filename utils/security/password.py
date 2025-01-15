from typing import List
from utils.config import Config


def validate_password_strength(password: str) -> List[str]:
    """Validate password strength and return a list of errors.
    
    Args:
        password: Password string to validate
        
    Returns:
        List of validation error messages, empty if password is valid
    """
    errors = []
    
    if len(password) < Config.PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {Config.PASSWORD_MIN_LENGTH} characters long.")
    
    if Config.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter.")
    
    if Config.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter.")
    
    if Config.PASSWORD_REQUIRE_NUMBER and not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one number.")
    
    if Config.PASSWORD_REQUIRE_SPECIAL_CHAR and not any(c in '!@#$%^&*(),.?":{}|<>' for c in password):
        errors.append("Password must contain at least one special character.")
    
    return errors