
class FetchError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'FetchError';
        this.status = status;
        this.data = data;
    }
}

window.utils = {
    getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    },

    async fetchWithCSRF(url, options = {}) {
        try {
            const csrfToken = this.getCSRFToken();
            const defaultHeaders = {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            };

            // Only add Azure token if it exists
            if (window.CHAT_CONFIG?.azureToken) {
                defaultHeaders['X-Azure-Token'] = window.CHAT_CONFIG.azureToken;
            }

            // Properly handle request body and content type
            let finalBody = options.body;
            if (finalBody && !(finalBody instanceof FormData)) {
                if (typeof finalBody === 'object') {
                    finalBody = JSON.stringify({
                        ...finalBody,
                        csrf_token: csrfToken
                    });
                    defaultHeaders['Content-Type'] = 'application/json';
                }
            }

            const finalHeaders = {
                ...defaultHeaders,
                ...options.headers
            };

            const response = await fetch(url, {
                method: options.method || 'POST',  // Ensure POST is used by default
                ...options,
                body: finalBody,
                headers: finalHeaders,
                credentials: 'same-origin'
            });

            let data;
            const contentType = response.headers.get('content-type');
            try {
                if (contentType?.includes('application/json')) {
                    data = await response.json();
                } else {
                    data = await response.text();
                }
            } catch (parseError) {
                throw new FetchError(
                    'Failed to parse response',
                    response.status,
                    await response.text()
                );
            }

            if (!response.ok) {
                throw new FetchError(
                    typeof data === 'object' && data.error ? data.error : `Request failed with status ${response.status}`,
                    response.status,
                    data
                );
            }

            return data;
        } catch (error) {
            if (error instanceof FetchError) {
                throw error;
            }
            throw new FetchError(error.message, 0, null);
        }
    },

    showFeedback(message, type = 'success', options = {}) {
        const { duration = 5000, position = 'top' } = options;
        let container = document.getElementById('feedback-container');

        if (!container) {
            container = document.createElement('div');
            container.id = 'feedback-container';
            container.className = 'fixed z-[1300] flex flex-col items-center space-y-2';
            document.body.appendChild(container);
        }

        const positionClasses = {
            top: 'top-24 left-1/2 transform -translate-x-1/2',
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
            <span class="flex-grow">${this.sanitizeHTML(message)}</span>
            <button class="ml-3 focus:outline-none hover:opacity-75" aria-label="Dismiss">
                <i class="fas fa-times"></i>
            </button>
        `;

        container.appendChild(messageElement);

        const dismiss = () => {
            messageElement.classList.add('opacity-0', 'scale-95');
            setTimeout(() => {
                if (messageElement.parentNode) {
                    messageElement.parentNode.removeChild(messageElement);
                }
                if (container.children.length === 0 && container.parentNode) {
                    container.parentNode.removeChild(container);
                }
            }, 300);
        };

        messageElement.querySelector('button').addEventListener('click', dismiss);

        if (type !== 'error' && duration > 0) {
            setTimeout(dismiss, duration);
        }

        return dismiss;
    },

    async checkAuth() {
        try {
            const response = await this.fetchWithCSRF('/auth/check');
            return response?.authenticated === true;
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
        let lastFunc;
        let lastRan;
        return function (...args) {
            if (!inThrottle) {
                func.apply(this, args);
                lastRan = Date.now();
                inThrottle = true;
            } else {
                clearTimeout(lastFunc);
                lastFunc = setTimeout(() => {
                    if ((Date.now() - lastRan) >= limit) {
                        func.apply(this, args);
                        lastRan = Date.now();
                    }
                }, limit - (Date.now() - lastRan));
            }
        };
    },

    formatDate(dateString) {
        if (!dateString) return '';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return '';
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            console.error('Date formatting error:', e);
            return '';
        }
    },

    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            this.showFeedback('Copied to clipboard!', 'success');
        } catch (err) {
            console.error('Copy failed:', err);
            this.showFeedback('Failed to copy to clipboard', 'error');
            throw err;
        }
    },

    async withLoading(element, callback, options = {}) {
        const originalContent = element.innerHTML;
        const loadingText = options.loadingText || 'Loading...';
        const loadingClass = options.loadingClass || 'opacity-50 cursor-wait';
        const loadingClasses = loadingClass.split(' ');

        try {
            element.disabled = true;
            element.classList.add(...loadingClasses);
            element.innerHTML = `
                <span class="inline-flex items-center">
                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    ${this.sanitizeHTML(loadingText)}
                </span>
            `;



const result = await callback();
return result;
        } finally {
    if (element) {
        element.disabled = false;
        element.classList.remove(...loadingClasses);
        element.innerHTML = originalContent;
    }
}
    },

validateForm(formElement, validationRules = {}) {
    const errors = {};
    if (!formElement) return { isValid: false, errors: { form: 'Form not found' } };

    const formData = new FormData(formElement);

    for (const [fieldName, rules] of Object.entries(validationRules)) {
        const value = formData.get(fieldName);

        if (rules.required && !value) {
            errors[fieldName] = 'This field is required';
            continue;
        }

        if (value) {
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
    }

    return {
        isValid: Object.keys(errors).length === 0,
        errors
    };
},

showValidationErrors(errors, formElement) {
    if (!formElement) return;

    // Remove existing error messages
    formElement.querySelectorAll('.error-message').forEach(el => el.remove());
    formElement.querySelectorAll('.error-field').forEach(el => {
        el.classList.remove('error-field', 'border-red-500');
    });

    // Add new error messages
    Object.entries(errors).forEach(([fieldName, message]) => {
        const field = formElement.querySelector(`[name="${fieldName}"]`);
        if (field) {
            field.classList.add('error-field', 'border-red-500');

            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message text-red-500 text-sm mt-1';
            errorDiv.textContent = message;

            field.parentNode.insertBefore(errorDiv, field.nextSibling);
        }
    });
},

formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0) return '0 Bytes';

    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
},

sanitizeHTML(html) {
    if (!html) return '';
    const div = document.createElement('div');
    div.textContent = html;
    return div.innerHTML;
},

parseJSON(jsonString, fallback = null) {
    if (!jsonString) return fallback;
    try {
        return JSON.parse(jsonString);
    } catch (e) {
        console.error('JSON parse error:', e);
        return fallback;
    }
},

getQueryParam(param) {
    if (!param) return null;
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
},

setQueryParam(param, value) {
    if (!param) return;
    const urlParams = new URLSearchParams(window.location.search);
    if (value === null || value === undefined) {
        urlParams.delete(param);
    } else {
        urlParams.set(param, value);
    }
    const newUrl = `${window.location.pathname}${urlParams.toString() ? '?' + urlParams.toString() : ''}`;
    window.history.replaceState({}, '', newUrl);
},

handleError(error) {
    console.error('Error:', error);

    let message = 'An unexpected error occurred';
    let type = 'error';

    if (error instanceof FetchError) {
        message = error.message;
        type = error.status >= 500 ? 'error' : 'warning';
    } else if (error instanceof Error) {
        message = error.message;
    }

    this.showFeedback(message, type);
    return { message, type };
}
};

// Export for module environments
if (typeof module !== 'undefined' && module.exports) {
    module.exports = window.utils;
}
