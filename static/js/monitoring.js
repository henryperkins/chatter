(() => {

    class Monitoring {
        constructor(options = {}) {
            this.options = {
                enabled: true,
                debugMode: window.CHAT_CONFIG?.debug || false,
                debugLog: true,
                errorReporting: true,
                performanceMonitoring: true,
                interactionTracking: true,
                maxLogEntries: 1000,
                ...options
            };

            this.logs = [];
            this.metrics = {
                errors: 0,
                apiCalls: 0,
                interactions: 0,
                renderTime: []
            };

            // Performance monitoring
            this.performance = {
                marks: new Map(),
                measures: []
            };

        }

        init() {
            if (!this.options.enabled) return;
            console.debug('Monitoring: Starting initialization');

            // Global error handling
            window.addEventListener('error', (event) => {
                console.debug('Monitoring: Caught global error', event);
                this.logError('Uncaught error', {
                    message: event.message,
                    filename: event.filename,
                    lineno: event.lineno,
                    colno: event.colno,
                    error: event.error
                });
            });

            // Promise rejection handling
            window.addEventListener('unhandledrejection', (event) => {
                this.logError('Unhandled promise rejection', {
                    reason: event.reason
                });
            });

            // Performance monitoring
            if (this.options.performanceMonitoring) {
                this.initPerformanceMonitoring();
            }

            // Interaction tracking
            if (this.options.interactionTracking) {
                this.initInteractionTracking();
            }

            // Network request monitoring
            this.initNetworkMonitoring();

            this.log('info', 'Monitoring initialized');
        }

        initPerformanceMonitoring() {
            // Monitor page load metrics
            if (window.performance) {
                window.addEventListener('load', () => {
                    const timing = performance.timing;
                    const metrics = {
                        pageLoad: timing.loadEventEnd - timing.navigationStart,
                        domReady: timing.domContentLoadedEventEnd - timing.navigationStart,
                        networkLatency: timing.responseEnd - timing.requestStart,
                        processingTime: timing.domComplete - timing.domLoading
                    };
                    this.logMetrics('Page Load Performance', metrics);
                });
            }

            // Monitor memory usage if available
            if (performance.memory) {
                setInterval(() => {
                    this.logMetrics('Memory Usage', {
                        usedJSHeapSize: performance.memory.usedJSHeapSize,
                        totalJSHeapSize: performance.memory.totalJSHeapSize
                    });
                }, 30000);
            }
        }

        initInteractionTracking() {
            const chatBox = document.getElementById('chat-box');
            const messageInput = document.getElementById('message-input');

            if (chatBox) {
                // Track message interactions
                chatBox.addEventListener('click', (e) => {
                    const target = e.target.closest('button');
                    if (target) {
                        this.logInteraction('Button clicked', {
                            buttonType: target.classList.contains('copy-button') ? 'copy' :
                                      target.classList.contains('regenerate-button') ? 'regenerate' : 'unknown'
                        });
                    }
                });
            }

            if (messageInput) {
                // Track message composition
                let compositionStart = 0;
                messageInput.addEventListener('focus', () => {
                    compositionStart = Date.now();
                });
                messageInput.addEventListener('blur', () => {
                    if (compositionStart) {
                        this.logInteraction('Message composition', {
                            duration: Date.now() - compositionStart,
                            length: messageInput.value.length
                        });
                    }
                });
            }
        }

        async logScrapeAction(url, success) {
            this.log('info', 'Scrape action', {
                url: url,
                success: success,
                timestamp: new Date().toISOString()
            });
        }

        initNetworkMonitoring() {
            // Monitor fetch requests
            const originalFetch = window.fetch;
            window.fetch = async (...args) => {
                const startTime = performance.now();
                try {
                    const response = await originalFetch(...args);
                    // Track scraping actions
                    if (args[0].includes('/scrape')) {
                        this.logScrapeAction(args[0], response.ok);
                    }
                    this.logApiCall('Fetch success', {
                        url: args[0],
                        duration: performance.now() - startTime,
                        status: response.status
                    });
                    return response;
                } catch (error) {
                    if (args[0].includes('/scrape')) {
                        this.logScrapeAction(args[0], false);
                    }
                    this.logApiCall('Fetch error', {
                        url: args[0],
                        duration: performance.now() - startTime,
                        error: error.message
                    });
                    throw error;
                }
            };

            // Monitor XHR requests
            const originalXHR = window.XMLHttpRequest.prototype.open;
            window.XMLHttpRequest.prototype.open = function(...args) {
                const startTime = performance.now();
                const self = this;
                this.addEventListener('load', () => {
                    window.monitoring.logApiCall('XHR complete', {
                        url: args[1],
                        duration: performance.now() - startTime,
                        status: self.status
                    });
                });
                return originalXHR.apply(this, args);
            };
        }

        mark(name) {
            if (!this.options.performanceMonitoring) return;
            const time = performance.now();
            this.performance.marks.set(name, time);
            if (this.options.debugMode) {
                console.debug(`[Performance] Mark: ${name} at ${time}ms`);
            }
        }

        measure(name, startMark, endMark) {
            if (!this.options.performanceMonitoring) return;
            const startTime = this.performance.marks.get(startMark);
            const endTime = this.performance.marks.get(endMark);
            if (startTime && endTime) {
                const duration = endTime - startTime;
                this.performance.measures.push({
                    name,
                    duration,
                    start: startTime,
                    end: endTime
                });
                if (this.options.debugMode) {
                    console.debug(`[Performance] Measure: ${name} = ${duration}ms`);
                }
            }
        }

        log(level, message, data = {}) {
            if (!this.options.enabled) return;

            if (this.options.debugLog) console.debug(`Monitoring [${level}]:`, message, data);
            const logEntry = {
                timestamp: new Date().toISOString(),
                level,
                message,
                data,
                url: window.location.href,
                sessionId: window.CHAT_CONFIG?.chatId || 'unknown'
            };

            this.logs.push(logEntry);
            if (this.logs.length > this.options.maxLogEntries) {
                this.logs.shift();
            }

            if (this.options.debugMode || level === 'error') {
                console[level](`[Monitoring] ${message}`, data);
            }

            // Send critical errors to server immediately
            if (level === 'error' && this.options.errorReporting) {
                this.reportError(logEntry);
            }
        }

        logError(message, error) {
            this.metrics.errors++;
            this.log('error', message, error);
        }

        logApiCall(message, data) {
            this.metrics.apiCalls++;
            this.log('info', message, data);
        }

        logInteraction(message, data) {
            this.metrics.interactions++;
            this.log('info', message, data);
        }

        logMetrics(name, metrics) {
            this.log('info', `Metrics: ${name}`, metrics);
        }

        async reportError(error) {
            try {
                await fetch('/api/log/error', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': window.CHAT_CONFIG?.csrfToken
                    },
                    body: JSON.stringify({
                        error,
                        userAgent: navigator.userAgent,
                        timestamp: new Date().toISOString(),
                        chatId: window.CHAT_CONFIG?.chatId,
                        userId: window.CHAT_CONFIG?.userId
                    })
                });
            } catch (e) {
                console.error('Failed to report error:', e);
            }
        }

        getMetrics() {
            return {
                ...this.metrics,
                performance: this.performance.measures,
                logs: this.logs.length
            };
        }

        getLogs(level = null) {
            return level ?
                this.logs.filter(log => log.level === level) :
                this.logs;
        }
    }

    // Export monitoring class
    window.Monitoring = Monitoring;

    // Expose debug functions when debug mode is enabled
    if (window.CHAT_CONFIG?.debug) {
        window.debugMonitoring = {
            getLogs: () => window.monitoring.getLogs(),
            getMetrics: () => window.monitoring.getMetrics(),
            clearLogs: () => window.monitoring.logs = [],
            toggleDebug: () => {
                window.monitoring.options.debugMode = !window.monitoring.options.debugMode;
                console.log(`Debug mode ${window.monitoring.options.debugMode ? 'enabled' : 'disabled'}`);
            }
        };
    }

    // Create instance but let core.js initialize it
    console.debug('Monitoring: Creating initial instance (disabled)');
    window.monitoring = new Monitoring({
        enabled: false, // Start disabled until core.js initializes
        debugLog: true  // Enable debug logging
    });
})();
