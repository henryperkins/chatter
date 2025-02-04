// static/js/utils.js

class FetchError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'FetchError';
        this.status = status;
        this.data = data;
    }
}

// Attach to window object immediately
window.utils = {
    getCSRFToken() {
        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        if (!token) {
            console.warn('CSRF token not found');
        }
        return token;
    },

    async fetchWithCSRF(url, options = {}) {
        try {
            const csrfToken = this.getCSRFToken();
            const headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken,
                ...options.headers
            };

            if (options.body && !(options.body instanceof FormData)) {
                headers['Content-Type'] = 'application/json';
                if (typeof options.body === 'object') {
                    options.body = JSON.stringify({
                        ...JSON.parse(JSON.stringify(options.body)),
                        csrf_token: csrfToken
                    });
                }
            }

            const response = await fetch(url, {
                ...options,
                headers,
                credentials: 'same-origin'
            });

            let data;
            const contentType = response.headers.get('content-type');
            if (contentType?.includes('application/json')) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            if (!response.ok) {
                throw new FetchError(
                    data.error || `HTTP error! status: ${response.status}`,
                    response.status,
                    data
                );
            }

            return data;
        } catch (error) {
            console.error('Fetch error:', error);
            throw error;
        }
    },

    showFeedback(message, type = 'success', options = {}) {
        const { duration = 5000, position = 'top' } = options;
        let container = document.getElementById('feedback-container');

        if (!container) {
            container = document.createElement('div');
            container.id = 'feedback-container';
            container.className = 'fixed z-50 flex flex-col items-center space-y-2';
            document.body.appendChild(container);
        }

        const positionClasses = {
            top: 'top-4 left-1/2 transform -translate-x-1/2',
            bottom: 'bottom-4 left-1/2 transform -translate-x-1/2',
            'top-right': 'top-4 right-4',
            'bottom-right': 'bottom-4 right-4'
        };

        const colorClasses = {
            success: 'bg-green-500 text-white',
            error: 'bg-red-500 text-white',
            warning: 'bg-yellow-500 text-black',
            info: 'bg-blue-500 text-white'
        };

        container.className = `fixed z-50 flex flex-col items-center space-y-2 ${positionClasses[position]}`;

        const messageElement = document.createElement('div');
        messageElement.className = `
            flex items-center justify-between px-4 py-2 rounded-lg shadow-lg
            ${colorClasses[type]} transition-all duration-300 transform
            hover:scale-105 max-w-md backdrop-blur-sm
        `;
        messageElement.innerHTML = `
            <span class="flex-grow">${message}</span>
            <button class="ml-3 focus:outline-none hover:opacity-75" aria-label="Dismiss">
                <i class="fas fa-times"></i>
            </button>
        `;

        container.appendChild(messageElement);

        const dismiss = () => {
            messageElement.classList.add('opacity-0', 'scale-95');
            setTimeout(() => {
                container.removeChild(messageElement);
                if (container.children.length === 0) {
                    document.body.removeChild(container);
                }
            }, 300);
        };

        messageElement.querySelector('button').addEventListener('click', dismiss);

        if (type !== 'error' && duration > 0) {
            setTimeout(dismiss, duration);
        }
    },

    async checkAuth() {
        try {
            const response = await this.fetchWithCSRF('/auth/check');
            return response.authenticated === true;
        } catch (error) {
            console.error('Auth check failed:', error);
            return false;
        }
    },

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    copyToClipboard(text) {
        return navigator.clipboard.writeText(text)
            .then(() => this.showFeedback('Copied to clipboard!', 'success'))
            .catch(err => {
                console.error('Failed to copy:', err);
                this.showFeedback('Failed to copy to clipboard', 'error');
            });
    },

    async withLoading(element, callback, options = {}) {
        const originalContent = element.innerHTML;
        const loadingText = options.loadingText || 'Loading...';
        const loadingClass = options.loadingClass || 'opacity-50 cursor-wait';

        try {
            element.disabled = true;
            element.classList.add(...loadingClass.split(' '));
            element.innerHTML = `
                <span class="inline-flex items-center">
                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    ${loadingText}
                </span>
            `;

            const result = await callback();
            return result;
        } finally {
            element.disabled = false;
            element.classList.remove(...loadingClass.split(' '));
            element.innerHTML = originalContent;
        }
    },

    validateForm(formElement, validationRules = {}) {
        const errors = {};
        const formData = new FormData(formElement);

        for (const [fieldName, rules] of Object.entries(validationRules)) {
            const value = formData.get(fieldName);

            if (rules.required && !value) {
                errors[fieldName] = 'This field is required';
                continue;
            }

            if (rules.minLength && value.length < rules.minLength) {
                errors[fieldName] = `Must be at least ${rules.minLength} characters`;
            }

            if (rules.maxLength && value.length > rules.maxLength) {
                errors[fieldName] = `Must be no more than ${rules.maxLength} characters`;
            }

            if (rules.pattern && !new RegExp(rules.pattern).test(value)) {
                errors[fieldName] = rules.patternMessage || 'Invalid format';
            }

            if (rules.custom && typeof rules.custom === 'function') {
                const customError = rules.custom(value, formData);
                if (customError) {
                    errors[fieldName] = customError;
                }
            }
        }

        return {
            isValid: Object.keys(errors).length === 0,
            errors
        };
    },

    showValidationErrors(errors, formElement) {
        // Remove existing error messages
        formElement.querySelectorAll('.error-message').forEach(el => el.remove());
        formElement.querySelectorAll('.error-field').forEach(el => {
            el.classList.remove('error-field', 'border-red-500');
        });

        // Add new error messages
        for (const [fieldName, message] of Object.entries(errors)) {
            const field = formElement.querySelector(`[name="${fieldName}"]`);
            if (field) {
                field.classList.add('error-field', 'border-red-500');

                const errorDiv = document.createElement('div');
                errorDiv.className = 'error-message text-red-500 text-sm mt-1';
                errorDiv.textContent = message;

                field.parentNode.insertBefore(errorDiv, field.nextSibling);
            }
        }
    },

    formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];

        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    },

    sanitizeHTML(html) {
        const div = document.createElement('div');
        div.textContent = html;
        return div.innerHTML;
    },

    parseJSON(jsonString, fallback = null) {
        try {
            return JSON.parse(jsonString);
        } catch (e) {
            console.error('JSON parse error:', e);
            return fallback;
        }
    },

    getQueryParam(param) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(param);
    },

    setQueryParam(param, value) {
        const urlParams = new URLSearchParams(window.location.search);
        if (value === null) {
            urlParams.delete(param);
        } else {
            urlParams.set(param, value);
        }
        window.history.replaceState({}, '', `${window.location.pathname}?${urlParams}`);
    },

    handleError(error) {
        console.error('Error:', error);

        let message = 'An unexpected error occurred';

        if (error instanceof FetchError) {
            message = error.message;
        } else if (error instanceof Error) {
            message = error.message;
        }

        this.showFeedback(message, 'error');
    }
};
