// Add Provider page initialization
(() => {
    'use strict';

    function initializeProviderForm() {
        const form = document.getElementById("add-provider-form");
        if (form) {
            form.classList.add('provider-form');
            form.dataset.submitText = "Add Provider";
        }
    }

    // Export initialization function
    window.initializeProvider = initializeProviderForm;

    // Auto-initialize on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', initializeProviderForm);
})();
