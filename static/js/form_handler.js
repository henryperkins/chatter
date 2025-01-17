// form_handler.js

class ModelFormHandler {
    constructor() {
        this.utils = window['utils'] || {};
        this.initializeForms();
    }

    initializeForms() {
        document.addEventListener("DOMContentLoaded", () => {
            const form = document.getElementById("edit-model-form") || document.getElementById("add-model-form");
            if (form) {
                this.form = form;
                form.addEventListener("submit", async (e) => {
                    e.preventDefault();
                    await this.handleFormSubmit(e);
                });
            }
        });
    }

    async handleFormSubmit(event) {
        const form = event.target;
        const submitButton = form.querySelector('button[type="submit"]');
        const actionUrl = form.action;

        // Validate endpoint
        if (!actionUrl || !(actionUrl.includes('/edit/') || actionUrl.includes('/add-model'))) {
            console.error('Invalid form action URL:', actionUrl);
            this.utils.showFeedback("Invalid form configuration", "error");
            return;
        }

        console.group("Form Submission Debug");
        console.debug("Form submission started");
        console.debug("Form:", form);
        console.debug("Action URL:", actionUrl);
        console.debug("Form Data:", Object.fromEntries(new FormData(form)));
        console.debug("Form Dataset:", form.dataset);
        console.groupEnd();

        try {
            // Show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = `
                <span class="inline-flex items-center">
                    <span>Processing...</span>
                    <svg class="animate-spin ml-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0
                            3.042 1.135 5.824 3 7.938l3-2.647z">
                        </path>
                    </svg>
                </span>
            `;

            const formData = new FormData(form);
            const data = {};

            // Process form data with better type handling
            formData.forEach((value, key) => {
                let stringValue = "";
                if (typeof value === "string") {
                    stringValue = value;
                }

                // Handle numeric fields with proper null/empty handling
                if (["max_tokens", "max_completion_tokens", "version"].includes(key)) {
                    if (stringValue === "" || stringValue === null || stringValue === undefined || stringValue === "None") {
                        data[key] = null;
                    } else {
                        const parsed = parseFloat(stringValue);
                        data[key] = isNaN(parsed) ? null : parsed;
                    }
                }
                // Handle temperature field
                else if (key === "temperature") {
                    data[key] = stringValue ? parseFloat(stringValue) : null;
                }
                // Handle boolean fields
                else if (["requires_o1_handling", "is_default", "supports_streaming"].includes(key)) {
                    data[key] = stringValue === "on" || stringValue === "true";
                }
                // Handle other fields
                else {
                    data[key] = stringValue;
                }
                console.debug(`Processing form field: ${key} = ${stringValue}`);
            });

            // Remove 'api_key' from data if it's empty
            if (!data.api_key) {
                delete data.api_key;
            }

            // Handle o1-preview specific logic
            if (data.requires_o1_handling) {
                data.temperature = 1.0;
                data.supports_streaming = false;
            }

            // Ensure CSRF token is present
            const csrfToken = this.utils.getCSRFToken();
            if (!data.csrf_token && csrfToken) {
                data.csrf_token = csrfToken;
            }

            console.debug("Sending form data to:", actionUrl);
            let response;
            try {
                response = await this.utils.fetchWithCSRF(actionUrl, {
                    method: "POST",
                    body: JSON.stringify(data),
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });

                if (!response) {
                    throw new Error("No response received from server");
                }

                // Handle non-JSON responses
                const contentType = response.headers.get("content-type");
                if (!contentType || !contentType.includes("application/json")) {
                    const text = await response.text();
                    throw new Error(`Invalid response format: ${text}`);
                }

                const responseData = await response.json();

                if (responseData.success) {
                    this.utils.showFeedback("Model saved successfully", "success");
                    if (responseData.redirect) {
                        console.debug("Redirecting to:", responseData.redirect);
                        window.location.href = responseData.redirect;
                    } else {
                        console.warn("No redirect URL provided in response");
                        this.utils.showFeedback("Model saved but no redirect provided", "warning");
                    }
                } else {
                    let errorMessage = "Failed to save model";
                    if (responseData.error) {
                        errorMessage = responseData.error;
                    } else if (responseData.errors) {
                        // Format errors with field names
                        errorMessage = Object.entries(responseData.errors)
                            .map(([field, errors]) => {
                                const fieldName = field.replace(/_/g, ' ');
                                return `${fieldName}: ${errors.join(', ')}`;
                            })
                            .join('. ');
                    }

                    console.error("Form submission failed:", {
                        message: errorMessage,
                        errors: responseData.errors,
                        status: response.status
                    });

                    // Show detailed error feedback
                    this.utils.showFeedback(errorMessage, "error", {
                        duration: 10000, // Show for 10 seconds
                        position: "top"
                    });

                    // Display field-specific errors
                    this.displayFormErrors(form, responseData.errors);
                }
            } catch (error) {
                console.error("Network or response error:", error);
                this.utils.showFeedback("Network error occurred. Please try again.", "error");
                return;
            }
        } catch (error) {
            console.error("Form submission error:", error);
            this.utils.showFeedback("An unexpected error occurred", "error");
        } finally {
            submitButton.disabled = false;
            submitButton.innerHTML = form.dataset.submitText || "Save Model";
        }
    }

    displayFormErrors(form, errors) {
        // Clear previous errors
        form.querySelectorAll(".error-text").forEach((el) => el.remove());
        form.querySelectorAll(".border-red-500").forEach((el) =>
            el.classList.remove("border-red-500")
        );

        // Display new errors with improved formatting
        if (errors) {
            Object.entries(errors).forEach(([field, messages]) => {
                const input = form.querySelector(`[name="${field}"]`);
                const container = input?.closest('.mb-6') || input?.parentElement;

                if (input && container) {
                    // Add error styling
                    input.classList.add("border-red-500");

                    // Create error message container
                    const errorDiv = document.createElement("div");
                    errorDiv.className = "error-text text-red-500 text-sm mt-1 space-y-1";

                    // Add each error message
                    messages.forEach(message => {
                        const errorMessage = document.createElement("div");
                        errorMessage.textContent = message;
                        errorDiv.appendChild(errorMessage);
                    });

                    // Insert after input or at end of container
                    container.appendChild(errorDiv);

                    // Scroll to first error if needed
                    if (Object.keys(errors)[0] === field) {
                        input.scrollIntoView({
                            behavior: 'smooth',
                            block: 'center'
                        });
                    }
                }
            });
        }
    }
}

document.addEventListener("DOMContentLoaded", function() {
    // Initialize form handler
    window['modelFormHandler'] = new ModelFormHandler();
});