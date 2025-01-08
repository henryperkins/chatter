// static/js/form_handler.js

document.addEventListener('DOMContentLoaded', () => {
    // Attach event listeners to all forms with the class 'ajax-form'
    document.querySelectorAll('.ajax-form').forEach((form) => {
        form.addEventListener('submit', handleFormSubmit);
    });

    // Function to handle form submissions
    async function handleFormSubmit(event) {
        event.preventDefault(); // Prevent the default form submission
        const form = event.target;
        const formData = new FormData(form);

        // Clear previous errors
        clearErrors(form);

        // Show loading spinner
        showLoadingSpinner(form);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000); // 15-second timeout

        try {
            const response = await fetch(form.action, {
                method: form.method,
                body: formData,
                headers: {
                    'X-CSRFToken': getCSRFToken(),
                },
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            let data;
            try {
                data = await response.json();
            } catch (jsonError) {
                // Non-JSON response handling
                const errorText = await response.text();
                showFeedback(`Server Error ${response.status}: ${errorText}`, 'error');
                return;
            }

            if (response.ok && data.success) {
                // Handle successful form submission
                showFeedback(data.message || 'Operation successful!', 'success');
                if (data.redirect) {
                    window.location.href = data.redirect; // Redirect if needed
                }
            } else {
                // Handle errors returned from the backend
                if (data.errors) {
                    displayErrors(form, data.errors); // Display validation errors
                } else {
                    showFeedback(data.error || 'An error occurred.', 'error');
                }
            }
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                showFeedback('Request timed out. Please try again.', 'error');
            } else {
                // Handle network or unexpected errors
                console.error('Error submitting form:', error);
                showFeedback(`An error occurred: ${error.message}`, 'error');
            }
        } finally {
            // Hide loading spinner
            hideLoadingSpinner(form);
        }
    }

    // Function to clear previous errors
    function clearErrors(form) {
        const errorElements = form.querySelectorAll('.error-text');
        errorElements.forEach((el) => el.remove());

        const inputFields = form.querySelectorAll('.border-red-500');
        inputFields.forEach((el) => el.classList.remove('border-red-500'));
    }

    // Function to display validation errors
    function displayErrors(form, errors) {
        for (const [fieldName, errorMessages] of Object.entries(errors)) {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field) {
                field.classList.add('border-red-500'); // Highlight the field with an error

                const errorText = document.createElement('p');
                errorText.className = 'text-red-500 text-xs mt-1 error-text';
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
            submitButton.innerHTML = submitButton.dataset.originalText || 'Submit';
            submitButton.disabled = false; // Re-enable the button
        }
    }

});