// csrf_handler.js
import axios from './lib/axios.min.js';

// Initialize axios defaults
axios.defaults.xsrfCookieName = 'X-CSRF-TOKEN';
axios.defaults.xsrfHeaderName = 'X-CSRFToken';
axios.defaults.withCredentials = true;

export class CSRFHandler {
    static getToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    static updateToken(newToken) {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            metaTag.content = newToken;
        }
        document.cookie = `X-CSRF-TOKEN=${newToken}; Path=/; Secure; SameSite=Strict`;
    }

    static async handleCSRFError(error) {
        if (error.response && error.response.status === 403 && error.response.data?.csrf_token) {
            // Update CSRF token from response
            CSRFHandler.updateToken(error.response.data.csrf_token);
            
            // Retry original request with new token
            const config = error.config;
            config.headers['X-CSRFToken'] = error.response.data.csrf_token;
            return axios(config);
        }
        return Promise.reject(error);
    }

    static initialize() {
        // Add response interceptor
        axios.interceptors.response.use(
            response => response,
            error => CSRFHandler.handleCSRFError(error)
        );
    }
}

// Initialize automatically when loaded
CSRFHandler.initialize();
