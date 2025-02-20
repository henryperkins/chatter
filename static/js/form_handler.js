// form_handler.js

class FormHandler {
    constructor() {
        this.initialized = false;
        this.requiredBooleanFields = [
            'requires_o1_handling',
            'is_default',
            'supports_streaming'
        ];
        
        if (window.utils) {
            console.debug('FormHandler: Utils already available, initializing...');
            this.init();
        } else {
            console.debug('FormHandler: Waiting for utils...');
            document.addEventListener('utils:ready', () => {
                console.debug('FormHandler: Utils ready, initializing...');
                this.init();
            });
        }
    }

    async init() {
        if (this.initialized) return;
        
        try {
            if (!window.utils) throw new Error('Utils not initialized');
            
            this.utils = window.utils;
            this.initialized = true;
            this.initializeForms();
            
            console.debug('FormHandler initialized successfully');
            return true;
        } catch (error) {
            console.error('FormHandler initialization failed:', error);
            this.initialized = false;
            return false;
        }
    }

    initializeForms() {
        const forms = document.querySelectorAll('form[method="POST"]');
        console.debug('FormHandler: Found forms:', forms.length);
        
        const boundSubmitHandler = this.handleSubmit.bind(this);
        
        forms.forEach(form => {
            // Store the bound handler on the form element
            form._submitHandler = boundSubmitHandler;
            
            // Remove any existing handlers
            form.removeEventListener('submit', form._submitHandler);
            
            // Add the new handler
            form.addEventListener('submit', form._submitHandler);
            
            console.debug('FormHandler: Initialized form:', {
                id: form.id,
                isAjax: form.dataset.ajax === 'true',
                method: form.method,
                action: form.action
            });
        });
    }

    handleSubmit(e) {
        const form = e.target;
        const isAjax = form.dataset.ajax === 'true';
        
        console.debug('FormHandler: Form submit triggered:', {
            id: form.id,
            isAjax: isAjax,
            method: form.method,
            action: form.action
        });

        if (!isAjax) {
            console.debug('FormHandler: Regular form submit, continuing...');
            return;
        }

        console.debug('FormHandler: AJAX form submit, handling...');
        e.preventDefault();
        e.stopPropagation();

        // Ensure we're initialized
        if (!this.initialized || !this.utils) {
            console.error('FormHandler not properly initialized');
            return;
        }

        this.handleFormSubmit(e).catch(error => {
            console.error('Form submission failed:', error);
            this.utils.showFeedback('Form submission failed. Please try again.', 'error');
        });
    }

    async handleFormSubmit(event) {
        const form = event.target;
        const submitButton = form.querySelector('button[type="submit"]');
        const actionUrl = form.action;
        let response;

        const isLoginForm = form.id === 'login-form';
        try {
            // Show loading state
            this.setLoadingState(submitButton, true);

            // Get form data
            const formData = new FormData(form);
            
            // Ensure CSRF token is present
            if (!formData.get('csrf_token')) {
                const csrfToken = this.utils.getCSRFToken();
                formData.append('csrf_token', csrfToken);
            }

            // Special handling for login form
            if (isLoginForm && !formData.get('remember')) {
                formData.append('remember', 'false');
            }

            // Add CSRF token from meta tag as header
            const csrfToken = this.utils.getCSRFToken();
            if (!csrfToken) {
                throw new Error('CSRF token not found. Please refresh the page.');
            }

            const headers = new Headers({
                'X-CSRF-TOKEN': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            });

            // Send request with form data directly
            response = await fetch(actionUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: headers,
                body: formData,
                mode: 'same-origin'
            });

            // Log response details for debugging
            console.debug('Form submission response:', {
                status: response.status,
                statusText: response.statusText,
                headers: Object.fromEntries(response.headers.entries())
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const responseData = await response.json();

            if (responseData.success) {
                this.handleSuccess(responseData);
            } else {
                this.handleErrors(form, responseData);
            }
        } catch (error) {
            // Enhanced error handling for CSRF failures
            if (error.message.includes('CSRF')) {
                this.handleSubmissionError(new Error('Security validation failed. Please refresh the page.'));
                return;
            }
            this.handleSubmissionError(error);
        } finally {
            this.setLoadingState(submitButton, false);
        }
    }

    handleSuccess(responseData) {
        if (responseData.message) {
            this.utils.showFeedback(responseData.message, 'success');
        }

        if (responseData.redirect) {
            // For login form, redirect immediately
            if (responseData.session_token) {
                window.location.href = responseData.redirect;
            } else {
                // For other forms, show message then redirect
                setTimeout(() => {
                    window.location.href = responseData.redirect;
                }, 1500);
            }
        }
    }

    fieldLabel(fieldName) {
        const labels = {
            // Login form fields
            'username': 'Username',
            'password': 'Password',
            'remember': 'Remember Me',
            'login': 'Login',
            // Other form fields
            'api_endpoint': 'API Endpoint',
            'api_key': 'API Key',
            'max_completion_tokens': 'Max Completion Tokens',
            'requires_o1_handling': 'o1-preview Handling',
            'supports_streaming': 'Streaming Support'
        };

        return labels[fieldName] || fieldName.replace(/_/g, ' ').capitalize();
    }

    handleErrors(form, responseData) {
        let errorMessages = [];

        // Handle single error message
        if (responseData.error) {
            errorMessages.push(responseData.error);
        }

        // Handle error object with multiple errors
        if (responseData.errors) {
            // Handle form-level errors first
            if (responseData.errors.form) {
                errorMessages.push(...responseData.errors.form);
                delete responseData.errors.form;  // Remove form errors so they don't get displayed twice
            }

            // Handle field-specific errors
            const fieldErrors = Object.entries(responseData.errors)
                .filter(([field, errors]) => errors && errors.length > 0)
                .map(([field, errors]) => {
                    const label = this.fieldLabel(field);
                    return `${label}: ${errors.join(', ')}`;
                });

            if (fieldErrors.length > 0) {
                errorMessages.push(...fieldErrors);
            }

            // Display field errors in the form
            this.displayFormErrors(form, responseData.errors);
        }

        // If no error messages were collected, show a generic error
        if (errorMessages.length === 0) {
            errorMessages.push('An unexpected error occurred. Please try again.');
        }

        // Show all error messages
        this.utils.showFeedback(errorMessages.join('. '), 'error', {
            duration: 10000,
            position: 'top'
        });
    }

    displayFormErrors(form, errors) {
        // Clear previous errors
        form.querySelectorAll('.error-text').forEach(el => el.remove());
        form.querySelectorAll('.border-red-500').forEach(el =>
            el.classList.remove('border-red-500', 'dark:border-red-600')
        );

        // Clear form-level error message
        const errorMessageDiv = form.parentElement.querySelector('#error-message');
        if (errorMessageDiv) {
            errorMessageDiv.textContent = '';
        }

        // Handle form-level errors first
        if (errors.form && errorMessageDiv) {
            errorMessageDiv.textContent = Array.isArray(errors.form) ? errors.form.join('. ') : errors.form;
            delete errors.form;  // Remove form errors so they don't get displayed with field errors
        }

        // Add field-specific errors
        Object.entries(errors).forEach(([field, messages]) => {
            const input = form.querySelector(`[name="${field}"]`);
            const container = input?.closest('.mb-6') || input?.parentElement;

            if (input && container) {
                input.classList.add('border-red-500', 'dark:border-red-600');
                const errorDiv = document.createElement('div');
                errorDiv.className = 'error-text text-red-500 dark:text-red-400 text-sm mt-1 space-y-1';
                errorDiv.innerHTML = Array.isArray(messages)
                    ? messages.join('<br>')
                    : messages;
                container.appendChild(errorDiv);
            }
        });
    }

    handleSubmissionError(error) {
        console.error('Form submission error:', error);
        const errorMessage = error.message || 'An unexpected error occurred. Please check your connection and try again.';
        
        // Show error in feedback toast
        this.utils.showFeedback(errorMessage, 'error');
        
        // Show error in form error message div
        const form = document.querySelector('form[data-ajax="true"]');
        if (form) {
            const errorMessageDiv = form.parentElement.querySelector('#error-message');
            if (errorMessageDiv) {
                errorMessageDiv.textContent = errorMessage;
            }
            
            // Clear any existing field errors
            form.querySelectorAll('.error-text').forEach(el => el.remove());
            form.querySelectorAll('.border-red-500').forEach(el =>
                el.classList.remove('border-red-500', 'dark:border-red-600')
            );
        }
    }

    setLoadingState(button, isLoading) {
        const spinner = button.querySelector('#loading-spinner');
        const buttonText = button.querySelector('#button-text');
        
        if (isLoading) {
            button.disabled = true;
            if (spinner) spinner.classList.remove('hidden');
            if (buttonText) buttonText.textContent = 'Processing...';
        } else {
            button.disabled = false;
            if (spinner) spinner.classList.add('hidden');
            if (buttonText) buttonText.textContent = button.closest('form').dataset.submitText || 'Submit';
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    window.formHandler = new FormHandler();
});

// Helper to capitalize strings
String.prototype.capitalize = function() {
    return this.charAt(0).toUpperCase() + this.slice(1);
};
