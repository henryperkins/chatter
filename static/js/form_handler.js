
class ModelFormHandler {
    constructor() {
        this.utils = window.utils || {};
        this.initializeForms();
    }

    initializeForms() {
        document.addEventListener("DOMContentLoaded", () => {
            document.querySelectorAll(".model-form").forEach(form => {
                form.addEventListener("submit", this.handleFormSubmit.bind(this));
            });
        });
    }

    async handleFormSubmit(event) {
        event.preventDefault();
        const form = event.target;
        const submitButton = form.querySelector('button[type="submit"]');
        const modelId = form.dataset.modelId;
        const actionUrl = `/edit/${modelId}`;
        
        if (!actionUrl || !modelId) {
            console.error('Form action URL or model ID not found');
            return;
        }

        console.debug('Form submission started:', {
            actionUrl,
            modelId,
            formData: new FormData(form)
        });
        
        try {
            // Show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = `
                <span class="inline-flex items-center">
                    <span>Processing...</span>
                    <span class="ml-2">
                        <svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    </span>
                </span>
            `;

            const formData = new FormData(form);
            const numericFields = ['max_tokens', 'max_completion_tokens', 'temperature', 'version'];
            const booleanFields = ['requires_o1_handling', 'is_default', 'supports_streaming'];

            // Process form data
            for (const [key, value] of formData.entries()) {
                if (numericFields.includes(key)) {
                    formData.set(key, Number(value));
                } else if (booleanFields.includes(key)) {
                    formData.set(key, value === 'on' || value === 'true');
                }
                console.debug(`Processing form field: ${key} = ${value}`);
            }

            // Ensure CSRF token is present
            if (!formData.get('csrf_token')) {
                const csrfToken = this.utils.getCSRFToken();
                formData.append('csrf_token', csrfToken);
                console.debug('Added CSRF token to form data');
            }

            // Handle o1-preview specific logic
            if (formData.get('requires_o1_handling')) {
                formData.set('temperature', 1.0);
                formData.set('supports_streaming', false);
            }

            console.debug('Sending form data to:', actionUrl);
            const response = await this.utils.fetchWithCSRF(actionUrl, {
                method: "POST",
                body: formData,
                headers: {
                    "X-CSRFToken": this.utils.getCSRFToken(),
                    "X-Requested-With": "XMLHttpRequest"
                }
            });
            console.debug('Received response:', response);

            if (response.success) {
                this.utils.showFeedback("Model saved successfully", "success");
                if (response.redirect) {
                    console.debug("Redirecting to:", response.redirect);
                    // Ensure redirect URL is absolute
                    const redirectUrl = response.redirect.startsWith('/') ? 
                        window.location.origin + response.redirect :
                        response.redirect;
                    setTimeout(() => {
                        window.location.href = redirectUrl;
                    }, 500);
                }
            } else {
                this.utils.showFeedback(response.error || "Failed to save model", "error");
                this.displayFormErrors(form, response.errors);
            }
        } catch (error) {
            console.error("Form submission error:", error);
            this.utils.showFeedback("An unexpected error occurred", "error");
        } finally {
            submitButton.disabled = false;
            submitButton.innerHTML = `
                <span>${form.dataset.submitText || "Submit"}</span>
            `;
        }
    }

    displayFormErrors(form, errors) {
        // Clear previous errors
        form.querySelectorAll('.error-text').forEach(el => el.remove());
        form.querySelectorAll('.border-red-500').forEach(el => el.classList.remove('border-red-500'));

        // Display new errors
        if (errors) {
            Object.entries(errors).forEach(([field, messages]) => {
                const input = form.querySelector(`[name="${field}"]`);
                if (input) {
                    input.classList.add('border-red-500');
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'error-text text-red-500 text-sm mt-1';
                    errorDiv.textContent = messages[0];
                    input.parentNode.appendChild(errorDiv);
                }
            });
        }
    }
}

// Initialize form handler
window.modelFormHandler = new ModelFormHandler();
