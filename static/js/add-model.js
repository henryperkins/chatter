// Add Model page initialization and handlers
(() => {
    'use strict';

    const { logDebug, logError } = window.addModelDebug || {
        logDebug: console.log,
        logError: console.error
    };

    function initializeAddModelForm() {
        const form = document.getElementById("add-model-form");
        if (form) {
            logDebug('Form found', { id: form.id });
            form.classList.add('model-form');
            form.dataset.submitText = "Add Model";

            // Initialize form validation and event handlers
            setupFormValidation(form);
            setupEventListeners(form);
        }
    }

    // Export initialization function
    window.initializeAddModel = initializeAddModelForm;

    // Auto-initialize on DOMContentLoaded
    document.addEventListener('app:ready', initializeAddModelForm);
})();
