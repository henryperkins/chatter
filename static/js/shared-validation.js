// Shared validation functions for forms
class FormValidator {
    static validateUsername(username) {
        const errors = [];
        if (!username.trim()) errors.push('Username is required');
        if (username.length < 4) errors.push('Username must be at least 4 characters');
        if (!/^[a-zA-Z0-9_]+$/.test(username)) errors.push('Invalid username format');
        return errors;
    }

    static validateEmail(email) {
        const errors = [];
        if (!email.trim()) errors.push('Email is required');
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.push('Invalid email format');
        return errors;
    }

    static validatePassword(password) {
        const errors = [];
        if (!password) errors.push('Password is required');
        if (password.length < 8) errors.push('Password must be at least 8 characters');
        if (!/[A-Z]/.test(password)) errors.push('Password needs an uppercase letter');
        if (!/[a-z]/.test(password)) errors.push('Password needs a lowercase letter');
        if (!/[0-9]/.test(password)) errors.push('Password needs a number');
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) errors.push('Password needs a special character');
        return errors;
    }

    static validateConfirmPassword(password, confirmPassword) {
        const errors = [];
        if (password !== confirmPassword) errors.push('Passwords do not match');
        return errors;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FormValidator;
} else {
    window.FormValidator = FormValidator;
}
