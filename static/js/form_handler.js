// Remove TypeScript-specific syntax and use JSDoc for type annotations

class ModelFormHandler {
    constructor() {
        this.utils = window.utils || {};
        this.initializeForms();
    }

    initializeForms() {
        document.addEventListener("DOMContentLoaded", () => {
            const form = document.getElementById("edit-model-form");
            if (form) {
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
        if (!actionUrl || !actionUrl.includes('/models/edit/')) {
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
            const data = {};

            // Process form data
            formData.forEach((value, key) => {
                let stringValue = "";
                if (typeof value === "string") {
                    stringValue = value;
                } else if (value instanceof File) {
                    stringValue = "";
                }

                // Handle numeric fields
                if (["max_tokens", "max_completion_tokens", "version"].includes(key)) {
                    if (stringValue === "" || stringValue === null || stringValue === undefined) {
                        data[key] = null;
                    } else if (!isNaN(stringValue)) {
                        data[key] = parseInt(stringValue, 10);
                    } else {
                        data[key] = null;
                    }
                }
                // Handle temperature field
                else if (key === "temperature") {
                    data[key] = stringValue ? parseFloat(stringValue) : null;
                }
                // Handle boolean fields
                else if (
                    ["requires_o1_handling", "is_default", "supports_streaming"].includes(
                        key
                    )
                ) {
                    data[key] = stringValue === "on" || stringValue === "true";
                }
                // Handle other fields
                else {
                    data[key] = stringValue;
                }
                console.debug(`Processing form field: ${key} = ${stringValue}`);
            });

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
            const response = await this.utils.fetchWithCSRF(actionUrl, {
                method: "POST",
                body: JSON.stringify(data),
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            console.debug("Received response:", response);

            console.debug("Server Response:", response);
            
            if (!response) {
                throw new Error("No response received from server");
            }

            if (response.success) {
                this.utils.showFeedback("Model saved successfully", "success");
                if (response.redirect) {
                    console.debug("Redirecting to:", response.redirect);
                    window.location.href = response.redirect;
                } else {
                    console.warn("No redirect URL provided in response");
                    this.utils.showFeedback("Model saved but no redirect provided", "warning");
                }
            } else {
                let errorMessage = "Failed to save model";
                if (response.error) {
                    errorMessage = response.error;
                } else if (response.errors) {
                    errorMessage = Object.values(response.errors)
                        .flat()
                        .join(". ");
                }
                
                console.error("Form submission failed:", errorMessage, response.errors);
                this.utils.showFeedback(errorMessage, "error");
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
        form.querySelectorAll(".error-text").forEach((el) => el.remove());
        form.querySelectorAll(".border-red-500").forEach((el) =>
            el.classList.remove("border-red-500")
        );

        // Display new errors
        if (errors) {
            Object.entries(errors).forEach(([field, messages]) => {
                const input = form.querySelector(`[name="${field}"]`);
                if (input) {
                    input.classList.add("border-red-500");
                    const errorDiv = document.createElement("div");
                    errorDiv.className = "error-text text-red-500 text-sm mt-1";
                    errorDiv.textContent = messages[0];
                    if (input.parentNode) {
                        input.parentNode.appendChild(errorDiv);
                    }
                }
            });
        }
    }
}

// Initialize form handler
window.modelFormHandler = new ModelFormHandler();
