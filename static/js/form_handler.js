(function() {
    console.log("Form handler initialized");

    // Utility function to get CSRF token
    function getCSRFToken() {
        const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
        return csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") || "" : "";
    }

    // Utility function to show feedback messages
    function showFeedback(message, type = "success") {
        console.log("Showing feedback:", message, type);
        const feedbackDiv = document.getElementById('feedback-message') || createFeedbackElement();
        feedbackDiv.className = `fixed top-4 left-1/2 transform -translate-x-1/2 p-4 rounded-lg shadow-lg z-50 ${
            type === 'success' ? 'bg-green-500' : 'bg-red-500'
        } text-white`;
        feedbackDiv.textContent = message;
        feedbackDiv.classList.remove('hidden');

        setTimeout(() => {
            feedbackDiv.classList.add('hidden');
        }, 3000);
    }

    function createFeedbackElement() {
        const div = document.createElement('div');
        div.id = 'feedback-message';
        document.body.appendChild(div);
        return div;
    }

    // Function to clear previous errors
    function clearErrors(form) {
        const errorElements = form.querySelectorAll(".error-text");
        errorElements.forEach((el) => el.remove());

        const inputFields = form.querySelectorAll(".border-red-500");
        inputFields.forEach((el) => el.classList.remove("border-red-500"));
    }

    // Function to display validation errors
    function displayErrors(form, errors) {
        for (const [fieldName, errorMessages] of Object.entries(errors)) {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field) {
                field.classList.add("border-red-500"); // Highlight the field with an error

                const errorText = document.createElement("p");
                errorText.className = "text-red-500 text-xs mt-1 error-text";
                errorText.textContent = errorMessages[0]; // Display the first error message

                field.parentNode.appendChild(errorText);
            }
        }
    }

    // Function to show a loading spinner
    function showLoadingSpinner(form) {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.dataset.originalText = submitButton.innerHTML;
            submitButton.innerHTML = `
                <svg class="animate-spin h-5 w-5 text-white mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                </svg>
            `;
            submitButton.disabled = true; // Disable the button during submission
        }
    }

    // Function to hide the loading spinner
    function hideLoadingSpinner(form) {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.innerHTML = submitButton.dataset.originalText || "Submit";
            submitButton.disabled = false; // Re-enable the button
        }
    }

    // Function to handle form submissions
    async function handleFormSubmit(event) {
        event.preventDefault(); // Prevent the default form submission
        console.log("Form submission started");

        const form = event.target;
        const formData = new FormData(form);

        // Convert numeric fields
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

        // Convert boolean fields
        const booleanFields = ["requires_o1_handling", "is_default"];
        for (const field of booleanFields) {
            const checkbox = form.querySelector(`[name="${field}"]`);
            if (checkbox) {
                formData.set(field, checkbox.checked);
            }
        }

        // Clear previous errors
        clearErrors(form);

        // Show loading spinner
        showLoadingSpinner(form);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000); // 15-second timeout

        try {
            console.log("Sending request");
            const response = await fetch(form.action, {
                method: form.method,
                body: formData,
                headers: {
                    "X-CSRFToken": getCSRFToken(),
                    Accept: "application/json",
                },
                signal: controller.signal,
            });
            console.log("Response received:", response.status);
            clearTimeout(timeoutId);

            let data;
            try {
                data = await response.json();
                console.log("Response data:", data);
            } catch (jsonError) {
                // Non-JSON response handling
                const errorText = await response.text();
                console.error("Non-JSON response error:", errorText);
                showFeedback(`Server Error ${response.status}: ${errorText}`, "error");
                return;
            }

            if (response.ok && data.success) {
                // Handle successful form submission
                console.log("Success, showing feedback");
                showFeedback(data.message || "Operation successful!", "success");
                if (data.redirect) {
                    console.log("Redirecting to:", data.redirect);
                    window.location.href = data.redirect; // Redirect if needed
                }
            } else {
                // Handle errors returned from the backend
                if (data.errors) {
                    console.log("API error (validation):", data.errors);
                    displayErrors(form, data.errors); // Display validation errors
                } else {
                    console.log("API error:", data.error);
                    showFeedback(data.error || "An error occurred.", "error");
                }
            }
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === "AbortError") {
                console.error("Request timed out:", error);
                showFeedback("Request timed out. Please try again.", "error");
            } else {
                // Handle network or unexpected errors
                console.error("Error submitting form:", error);
                showFeedback(`An error occurred: ${error.message}`, "error");
            }
        } finally {
            // Hide loading spinner
            hideLoadingSpinner(form);
        }
    }

    // Attach event listeners to all forms with the class 'ajax-form'
    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll(".ajax-form").forEach((form) => {
            form.addEventListener("submit", handleFormSubmit);
        });
    });
})();