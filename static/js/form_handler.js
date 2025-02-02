// form_handler.js

class ModelFormHandler {
    constructor() {
        this.utils = window['utils'] || {};
        this.requiredBooleanFields = [
            'requires_o1_handling', 
            'is_default', 
            'supports_streaming'
        ];
        this.initializeForms();
    }

    initializeForms() {
        document.addEventListener('DOMContentLoaded', () => {
            const forms = document.querySelectorAll('.model-form');
            forms.forEach(form => {
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    await this.handleFormSubmit(e);
                });
            });
        });
    }

    async handleFormSubmit(event) {
        const form = event.target;
        const submitButton = form.querySelector('button[type="submit"]');
        const actionUrl = form.action;
        let response;

        try {
            // Show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = this.loadingButtonHTML();

            // Process form data with proper type handling
            const formData = new FormData(form);
            const data = this.processFormData(formData);

            // Handle API key preservation
            if (!data.api_key || data.api_key.trim() === '') {
                delete data.api_key;
            }

            // Add CSRF token
            const csrfToken = this.utils.getCSRFToken();
            if (csrfToken) {
                data.csrf_token = csrfToken;
            }

            // Send request
            response = await this.sendFormRequest(actionUrl, data, csrfToken);
            
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
            this.handleSubmissionError(error);
        } finally {
            this.resetSubmitButton(submitButton, form);
        }
    }

    processFormData(formData) {
        const data = {};
        
        formData.forEach((value, key) => {
            data[key] = this.convertFormValue(key, value);
        });

        // Ensure all boolean fields are present
        this.requiredBooleanFields.forEach(field => {
            if (!(field in data)) {
                data[field] = false;
            }
        });

        return data;
    }

    convertFormValue(key, value) {
        // Handle numeric fields
        if (['max_tokens', 'max_completion_tokens'].includes(key)) {
            return this.parseNumericValue(value);
        }

        // Handle temperature field
        if (key === 'temperature') {
            return this.parseFloatValue(value);
        }

        // Handle boolean fields
        if (this.requiredBooleanFields.includes(key)) {
            return this.parseBooleanValue(value);
        }

        // Handle other string values
        return value.toString().trim();
    }

    parseNumericValue(value) {
        if (['', 'null', 'undefined', 'None'].includes(value)) return null;
        const parsed = parseInt(value);
        return isNaN(parsed) ? null : parsed;
    }

    parseFloatValue(value) {
        if (['', 'null', 'undefined', 'None'].includes(value)) return null;
        const parsed = parseFloat(value);
        return isNaN(parsed) ? null : parsed;
    }

    parseBooleanValue(value) {
        if (typeof value === 'boolean') return value;
        return ['on', 'true', '1'].includes(value.toLowerCase());
    }

    async sendFormRequest(url, data, csrfToken) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(data)
        });
    }

    handleSuccess(responseData) {
        this.utils.showFeedback(responseData.message || 'Model saved successfully', 'success');
        
        if (responseData.redirect) {
            setTimeout(() => {
                window.location.href = responseData.redirect;
            }, 1500);
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
    window.modelFormHandler = new ModelFormHandler();
});

// Helper to capitalize strings
String.prototype.capitalize = function() {
    return this.charAt(0).toUpperCase() + this.slice(1);
};
