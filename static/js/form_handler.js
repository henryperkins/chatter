(function() {
    console.log("Form handler initialized");

    // Access utility functions from window.utils
    const { getCSRFToken, showFeedback, fetchWithCSRF, showLoading, hideLoading, withLoading } = window.utils;

    /**
     * Clears previous error indicators from the form.
     * @param {HTMLFormElement} form 
     */
    function clearErrors(form) {
        const errorElements = form.querySelectorAll(".error-text");
        errorElements.forEach((el) => el.remove());

        const inputFields = form.querySelectorAll(".border-red-500");
        inputFields.forEach((el) => el.classList.remove("border-red-500"));
    }

    /**
     * Displays validation errors on the relevant form fields.
     * @param {HTMLFormElement} form 
     * @param {object} errors - A mapping: { fieldName: [errorMessage1, ...], ... }
     */
    function displayErrors(form, errors) {
        for (const [fieldName, errorMessages] of Object.entries(errors)) {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field) {
                field.classList.add("border-red-500"); // Highlight field with an error

                const errorText = document.createElement("p");
                errorText.className = "text-red-500 text-xs mt-1 error-text";
                errorText.textContent = errorMessages[0]; // display the first error message

                field.parentNode.appendChild(errorText);
            }
        }
    }

    /**
     * Handles the form submission via AJAX, leveraging fetchWithCSRF.
     * @param {Event} event
     */
    async function handleFormSubmit(event) {
        event.preventDefault(); // Prevent the default form submission
        console.log("Form submission started");

        const form = event.target;
        const formData = new FormData(form);

        // Convert numeric fields (example usage)
        for (const [key, value] of formData.entries()) {
            if (key === "max_completion_tokens" || key === "max_tokens") {
                const numValue = parseInt(value, 10);
                if (!isNaN(numValue)) {
                    formData.set(key, numValue);
                }
            } else if (key === "temperature") {
                const numValue = parseFloat(value);
                if (!isNaN(numValue)) {
                    formData.set(key, numValue);
                }
            }
        }

        // Convert certain fields to boolean
        const booleanFields = ["requires_o1_handling", "is_default"];
        for (const field of booleanFields) {
            const checkbox = form.querySelector(`[name="${field}"]`);
            if (checkbox) {
                formData.set(field, checkbox.checked);
            }
        }

        // Clear any old errors
        clearErrors(form);

        // Wrap our async operation with a spinner using 'withLoading'
        const submitButton = form.querySelector('button[type="submit"]');
        await withLoading(submitButton, async () => {
            try {
                console.log("Sending request via fetchWithCSRF");

                const data = await fetchWithCSRF(form.action, {
                    method: form.method || "POST",
                    body: formData,
                });

                console.log("Response data:", data);

                // Handle successful form submission
                if (data.success) {
                    console.log("Success, showing feedback");
                    showFeedback(data.message || "Operation successful!", "success");
                    if (data.redirect) {
                        console.log("Redirecting to:", data.redirect);
                        window.location.href = data.redirect; // redirect if needed
                    }
                } else {
                    // Handle backend-reported errors
                    if (data.errors) {
                        console.log("API error (validation):", data.errors);
                        displayErrors(form, data.errors);
                    } else {
                        console.log("API error:", data.error);
                        showFeedback(data.error || "An error occurred.", "error");
                    }
                }
            } catch (error) {
                if (error.name === "AbortError") {
                    console.error("Request timed out:", error);
                    showFeedback("Request timed out. Please try again.", "error");
                } else {
                    // Handle network or unexpected errors
                    console.error("Error submitting form:", error);
                    showFeedback(`An error occurred: ${error.message}`, "error");
                }
            }
        });
    }

    // Attach event listeners to all forms with the class 'ajax-form'
    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll(".ajax-form").forEach((form) => {
            form.addEventListener("submit", handleFormSubmit);
        });
    });
})();
