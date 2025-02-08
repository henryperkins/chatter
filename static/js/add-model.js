// Add Model page initialization and handlers
(() => {
    'use strict';

    const { logDebug, logError } = window.addModelDebug || {
        logDebug: console.log,
        logError: console.error
    };

    function setupFormValidation(form) {
        const validateForm = () => {
            const errors = [];
            const provider = form.querySelector('select[name="provider_id"]');
            const isAzureProvider = provider ? provider.options[provider.selectedIndex]?.text.toLowerCase().includes('azure') : false;

            // Validate required fields
            Array.from(form.elements).forEach(field => {
                if (!field.name) return;

                // Special handling for deployment_name field
                if (field.name === 'deployment_name') {
                    const deploymentNameDiv = field.closest('.deployment-name-section');
                    const isVisible = deploymentNameDiv.style.display !== 'none';

                    if (isAzureProvider && isVisible && !field.value.trim()) {
                        errors.push('Deployment name is required for Azure OpenAI providers');
                        field.classList.add('border-red-500', 'dark:border-red-600');
                    }
                } else if (field.required && !field.value) {
                    errors.push(`${field.name} is required`);
                    field.classList.add('border-red-500', 'dark:border-red-600');
                }
            });

            return errors;
        };

        form.addEventListener('submit', function(e) {
            const errors = validateForm();
            if (errors.length > 0 || !form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
                form.classList.add('was-validated');

                // Display errors
                errors.forEach(error => {
                    window.utils?.showFeedback(error, 'error');
                });
            }
        });
    }

    function setupEventListeners(form) {
        // Provider change handler
        const providerSelect = form.querySelector('select[name="provider_id"]');
        if (providerSelect) {
            providerSelect.addEventListener('change', async function() {
                const providerId = this.value;
                if (!providerId) return;

                try {
                    const response = await fetch(`/models/api/providers/${providerId}`);
                    const provider = await response.json();

                    // Update form based on provider type
                    updateFormForProvider(form, provider);
                } catch (error) {
                    logError('Error fetching provider details:', error);
                    window.utils?.showFeedback('Failed to load provider details', 'error');
                }
            });
        }

        // Model type change handler
        const modelTypeSelect = form.querySelector('select[name="model_type"]');
        const o1HandlingCheckbox = form.querySelector('input[name="requires_o1_handling"]');
        if (modelTypeSelect && o1HandlingCheckbox) {
            const updateForModelType = () => {
                const modelType = modelTypeSelect.value;
                const requiresO1 = o1HandlingCheckbox.checked;
                const isO1Preview = modelType === 'o1-preview' && requiresO1;

                updateFormForModelType(form, isO1Preview);
            };

            modelTypeSelect.addEventListener('change', updateForModelType);
            o1HandlingCheckbox.addEventListener('change', updateForModelType);
        }
    }

    function updateFormForProvider(form, provider) {
        const deploymentNameDiv = form.querySelector('.deployment-name-section');
        const apiVersionDiv = form.querySelector('.api-version-section');
        const apiKeyDiv = form.querySelector('.api-key-section');
        const azureEndpointInfo = form.querySelector('.azure-endpoint-info');
        const openaiEndpointInfo = form.querySelector('.openai-endpoint-info');
        const apiEndpointInput = form.querySelector('input[name="api_endpoint"]');

        // Show/hide deployment name field
        if (deploymentNameDiv) {
            deploymentNameDiv.style.display = provider.is_azure ? 'block' : 'none';
            const deploymentNameInput = deploymentNameDiv.querySelector('input');
            if (deploymentNameInput) {
                deploymentNameInput.required = provider.is_azure;
                deploymentNameInput.tabIndex = provider.is_azure ? 0 : -1;
            }
        }

        // Show/hide API version field
        if (apiVersionDiv) {
            apiVersionDiv.style.display = provider.is_azure ? 'block' : 'none';
        }

        // Show/hide API key field based on provider authentication requirement
        if (apiKeyDiv) {
            apiKeyDiv.style.display = provider.requires_authentication ? 'block' : 'none';
            const apiKeyInput = apiKeyDiv.querySelector('input');
            if (apiKeyInput) {
                apiKeyInput.required = provider.requires_authentication;
                apiKeyInput.tabIndex = provider.requires_authentication ? 0 : -1;
            }
        }

        // Show/hide endpoint info
        if (azureEndpointInfo) azureEndpointInfo.style.display = provider.is_azure ? 'block' : 'none';
        if (openaiEndpointInfo) openaiEndpointInfo.style.display = provider.is_azure ? 'none' : 'block';

        // Update API endpoint placeholder
        if (apiEndpointInput) {
            apiEndpointInput.placeholder = provider.is_azure
                ? "https://your-resource.openai.azure.com/openai/deployments/{deployment-name}/chat/completions?api-version=2024-12-01-preview"
                : "https://api.openai.com/v1/chat/completions";
        }
    }

    function updateFormForModelType(form, isO1Preview) {
        const temperatureInput = form.querySelector('input[name="temperature"]');
        const streamingCheckbox = form.querySelector('input[name="supports_streaming"]');
        const maxCompletionTokensInput = form.querySelector('input[name="max_completion_tokens"]');
        const standardModelNote = form.querySelector('.standard-model-note');
        const o1PreviewNote = form.querySelector('.o1-preview-note');
        const reasoningSettings = form.querySelector('.reasoning-settings');

        if (isO1Preview) {
            // Update temperature
            if (temperatureInput) {
                temperatureInput.value = '1.0';
                temperatureInput.disabled = true;
            }

            // Update streaming
            if (streamingCheckbox) {
                streamingCheckbox.checked = false;
                streamingCheckbox.disabled = true;
            }

            // Update max completion tokens
            if (maxCompletionTokensInput) {
                maxCompletionTokensInput.max = 8300;
                if (maxCompletionTokensInput.value > 8300) {
                    maxCompletionTokensInput.value = 8300;
                }
            }

            // Update token limit notes
            if (standardModelNote) standardModelNote.style.display = 'none';
            if (o1PreviewNote) o1PreviewNote.style.display = 'inline';

            // Show reasoning settings
            if (reasoningSettings) reasoningSettings.style.display = 'block';
        } else {
            // Reset fields for standard models
            if (temperatureInput) temperatureInput.disabled = false;
            if (streamingCheckbox) streamingCheckbox.disabled = false;
            if (maxCompletionTokensInput) maxCompletionTokensInput.max = 16384;
            if (standardModelNote) standardModelNote.style.display = 'inline';
            if (o1PreviewNote) o1PreviewNote.style.display = 'none';
            if (reasoningSettings) reasoningSettings.style.display = 'none';
        }
    }

    async function initializeAddModelForm() {
        // Wait for core app initialization
        if (!window.App?.initialized) {
            try {
                await window.App.waitForDependencies();
            } catch (error) {
                logError('Failed to initialize dependencies:', error);
                return;
            }
        }

        const form = document.getElementById("add-model-form");
        if (form) {
            logDebug('Form found', { id: form.id });
            form.classList.add('model-form');
            form.dataset.submitText = "Add Model";

            // Initialize form validation and event handlers
            setupFormValidation(form);
            setupEventListeners(form);

            // Verify CSRF token is available
            const csrfToken = window.utils?.getCSRFToken();
            if (!csrfToken) {
                logError('CSRF token not found');
                window.utils?.showFeedback('Security token not found. Please refresh the page.', 'error');
                return;
            }

            logDebug('Form initialized successfully', {
                hasCSRF: !!csrfToken,
                utils: !!window.utils
            });
        }
    }

    // Export initialization function
    window.initializeAddModel = initializeAddModelForm;

    // Auto-initialize on app:ready
    document.addEventListener('app:ready', initializeAddModelForm);
})();
