// form_handler.js

class FormHandler {
    constructor() {
        this.initialized = false;
        this.initPromise = this.init();
        this.requiredBooleanFields = [
            'requires_o1_handling',
            'is_default',
            'supports_streaming'
        ];
        
        // Wait for utils to be ready before initializing
        document.addEventListener('utils:ready', () => {
            console.debug('FormHandler: Utils ready, initializing...');
            this.init();
        });
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
        forms.forEach(form => {
            console.debug('FormHandler: Binding submit handler to form:', form.id);
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleFormSubmit(e);
            });
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
            submitButton.disabled = true;
            submitButton.innerHTML = this.loadingButtonHTML();

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
            const headers = {
                'X-CSRF-TOKEN': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            };

            // Send request with form data directly
            response = await fetch(actionUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: headers,
                body: formData
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
            this.resetSubmitButton(submitButton, form);
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

    handleErrors(form, responseData) {
        let errorMessage = 'Failed to save model';

        if (responseData.error) {
            errorMessage = responseData.error;
        } else if (responseData.errors) {
            errorMessage = Object.entries(responseData.errors)
                .map(([field, errors]) => `${this.fieldLabel(field)}: ${errors.join(', ')}`)
                .join('. ');

            this.displayFormErrors(form, responseData.errors);
        }

        this.utils.showFeedback(errorMessage, 'error', {
            duration: 10000,
            position: 'top'
        });
    }

    fieldLabel(fieldName) {
        const labels = {
            'api_endpoint': 'API Endpoint',
            'api_key': 'API Key',
            'max_completion_tokens': 'Max Completion Tokens',
            'requires_o1_handling': 'o1-preview Handling',
            'supports_streaming': 'Streaming Support'
        };

        return labels[fieldName] || fieldName.replace(/_/g, ' ').capitalize();
    }

    displayFormErrors(form, errors) {
        // Clear previous errors
        form.querySelectorAll('.error-text').forEach(el => el.remove());
        form.querySelectorAll('.border-red-500').forEach(el =>
            el.classList.remove('border-red-500', 'dark:border-red-600')
        );

        // Add new errors
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
        this.utils.showFeedback(
            'An unexpected error occurred. Please check your connection and try again.',
            'error'
        );
    }

    loadingButtonHTML() {
        return `
            <span class="inline-flex items-center">
                <span>Processing...</span>
                <svg class="animate-spin ml-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z">
                    </path>
                </svg>
            </span>
        `;
    }

    resetSubmitButton(button, form) {
        button.disabled = false;
        button.innerHTML = form.dataset.submitText || 'Save Model';
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
