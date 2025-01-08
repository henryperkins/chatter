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

        try {
            const response = await fetch(form.action, {
                method: form.method,
                body: formData,
                headers: {
                    'X-CSRFToken': getCSRFToken(), // Include CSRF token for security
                },
            });

            const data = await response.json();

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
            // Handle network or unexpected errors
            console.error('Error submitting form:', error);
            showFeedback('An unexpected error occurred. Please try again.', 'error');
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
            submitButton.innerHTML = `
                <svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
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

    // Function to show feedback messages (success/error)
    function showFeedback(message, type = 'success') {
        const feedbackDiv = document.getElementById('feedback-message');
        if (!feedbackDiv) return;

        feedbackDiv.innerHTML = `
            <div class="flex items-center justify-between">
                <span>${message}</span>
                ${type === 'error' ? '<button id="feedback-close" class="ml-4 text-lg">&times;</button>' : ''}
            </div>
        `;
        feedbackDiv.className = `fixed top-4 left-1/2 transform -translate-x-1/2 p-4 rounded-lg shadow-lg z-50 max-w-md w-full text-center ${
            type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
        }`;
        feedbackDiv.classList.remove('hidden');

        if (type === 'success') {
            setTimeout(() => feedbackDiv.classList.add('hidden'), 5000); // Hide success messages after 5 seconds
        } else {
            const closeButton = document.getElementById('feedback-close');
            if (closeButton) {
                closeButton.addEventListener('click', () => {
                    feedbackDiv.classList.add('hidden');
                });
            }
        }
    }

    // Function to get the CSRF token from the meta tag
    function getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    }
});