import { ChatConfig } from './chat-config.js';

class MessageRenderer {
    static templates = {
        assistant: null,
        user: null,
        attachment: null,
        attachmentItem: null,
        typingIndicator: null
    };

    static async initialize() {
        console.log('Initializing MessageRenderer with dependencies:', {
            md: !!window.md,
            DOMPurify: !!window.DOMPurify,
            Prism: !!window.Prism,
            CHAT_CONFIG: !!window.CHAT_CONFIG
        });

        // Cache templates from the DOM
        this.templates.assistant = document.getElementById('assistant-message-template');
        this.templates.user = document.getElementById('user-message-template');
        this.templates.attachment = document.getElementById('attachment-template');
        this.templates.attachmentItem = document.getElementById('attachment-item-template');
        this.templates.typingIndicator = document.getElementById('typing-indicator-template');

        if (!this.templates.assistant || !this.templates.user) {
            throw new Error('Message templates not found');
        }

        // Process existing messages
        const chatBox = document.getElementById('chat-box');
        if (chatBox) {
            const assistantMessages = chatBox.querySelectorAll('.assistant-message .prose');
            for (const messageDiv of assistantMessages) {
                const content = messageDiv.getAttribute('data-content');
                if (content) {
                    await this.finalizeAssistantMessage(messageDiv.closest('.assistant-message'), content);
                }
            }
        }

        // Dispatch event to signal MessageRenderer is ready
        document.dispatchEvent(new Event('messagerenderer:ready'));
    }

    static renderAssistantMessage(message, isStreaming = false) {
        const template = this.templates.assistant;
        const clone = template.content.cloneNode(true);
        const messageContainer = clone.firstElementChild;
        const messageContent = clone.querySelector('[data-role="assistant-message"]');
        const proseDiv = messageContent.querySelector('.prose');
        const timestamp = clone.querySelector('span.text-xs');
        const copyButton = clone.querySelector('.copy-button');

        // Handle both string and object message formats
        const content = typeof message === 'string' ? message : message.content;
        const contentHtml = typeof message === 'string' ? null : message.content_html;

        // Ensure content is never empty/undefined
        const displayContent = content || 'No response generated';

        // Add o-series class if needed
        messageContainer.classList.toggle('o-series-message', window.CHAT_CONFIG?.isOSeriesModel);

        // Set content - use pre-rendered HTML if available, otherwise use plain text
        if (contentHtml && !isStreaming) {
            proseDiv.innerHTML = contentHtml;
        } else {
            proseDiv.textContent = displayContent;
        }
        proseDiv.setAttribute('data-content', displayContent);

        // Show a timestamp
        timestamp.textContent = new Date().toLocaleTimeString();

        // If there's a copy button, store raw text
        if (copyButton) {
            copyButton.setAttribute('data-raw-content', content);
        }

        return clone.firstElementChild;
    }

    static renderUserMessage(content, files = []) {
        const template = this.templates.user;
        const clone = template.content.cloneNode(true);
        const messageText = clone.querySelector('p');
        const timestamp = clone.querySelector('span.text-xs');
        const copyButton = clone.querySelector('.copy-button');

        // Assign user content
        messageText.textContent = content;
        timestamp.textContent = new Date().toLocaleTimeString();

        // Set up copy button
        if (copyButton) {
            copyButton.setAttribute('data-raw-content', content);
        }

        // If user included attachments, render them
        if (files && files.length > 0) {
            const attachments = this.renderAttachments(files);
            messageText.parentNode.appendChild(attachments);
        }

        return clone.firstElementChild;
    }

    static renderAttachments(files) {
        const template = this.templates.attachment;
        const clone = template.content.cloneNode(true);
        const attachmentList = clone.querySelector('.attachment-list');

        // For each file, clone the attachment-item template
        files.forEach(file => {
            const itemTemplate = this.templates.attachmentItem;
            if (!itemTemplate) return; // fallback if template is missing

            const itemClone = itemTemplate.content.cloneNode(true);
            const nameSpan = itemClone.querySelector('.attachment-name');
            const link = itemClone.querySelector('.attachment-link');

            // File info
            nameSpan.textContent = file.name;
            if (file.url) {
                link.href = file.url;
            } else {
                link.remove(); // if no URL, remove the link entirely
            }

            attachmentList.appendChild(itemClone);
        });

        return clone;
    }

    static makeContentCollapsible(container, content) {
        const messageContent = container.closest('.message-content');
        if (!messageContent) return;

        const toggleButton = messageContent.querySelector('.toggle-more');
        if (!toggleButton) return;

        // Get the raw content length and rendered content height
        const rawLength = content.length;
        const lineCount = content.split('\n').length;
        const renderedHeight = container.scrollHeight;
        const hasCodeBlock = container.querySelector('pre');

        // Check if content is long enough to need collapsing
        const shouldCollapse = rawLength > 800 || 
                             lineCount > 15 || 
                             renderedHeight > 400 ||
                             (hasCodeBlock && (rawLength > 400 || lineCount > 10));

        if (shouldCollapse) {
            messageContent.classList.add('collapsed');
            toggleButton.classList.remove('hidden');

            // Ensure the toggle button is outside any code blocks
            toggleButton.style.position = 'relative';
            toggleButton.style.zIndex = '10';

            toggleButton.addEventListener('click', () => {
                messageContent.classList.toggle('collapsed');
                toggleButton.textContent = messageContent.classList.contains('collapsed') 
                    ? 'Show more' 
                    : 'Show less';
            });
        }
    }

    static async finalizeAssistantMessage(messageDiv, content) {
        if (!messageDiv) return;

        const container = messageDiv.querySelector('.prose');
        if (!container) return;

        // Enhanced markdown rendering for o-series models
        let renderedHtml = content;
        if (window.md) {
            window.md.set({ breaks: true });  // Enable line breaks
            if (window.CHAT_CONFIG?.isOSeriesModel) {
                content = this.preprocessOSeriesMarkdown(content);
            }
            renderedHtml = window.md.render(content);

            // Sanitize with DOMPurify
            renderedHtml = window.DOMPurify
              ? window.DOMPurify.sanitize(renderedHtml, {
                    ALLOWED_TAGS: [
                        'p','strong','em','ul','ol','li','code','pre','blockquote','a','span','div',
                        'h1','h2','h3','h4','h5','h6','hr','br','table','thead','tbody','tr','th','td',
                        'del','input'
                    ],
                    ALLOWED_ATTRS: {
                        a: ['href', 'title', 'target', 'rel', 'class'],
                        span: ['class'],
                        code: ['class'],
                        pre: ['class', 'data-language'],
                        div: ['class', 'style'],
                        table: ['class'],
                        th: ['class'],
                        td: ['class'],
                        input: ['type', 'checked', 'disabled'],
                        li: ['class']
                    },
                    ADD_ATTR: ['target'],
                    FORCE_BODY: true
                })
              : renderedHtml; // fallback if no DOMPurify

            // Insert sanitized HTML
            container.innerHTML = renderedHtml;
        }

        // Update the copy button's data-raw-content
        const copyButton = messageDiv.querySelector('.copy-button');
        if (copyButton) {
            copyButton.setAttribute('data-raw-content', content);
        }

        // Syntax highlighting
        if (window.Prism) {
            const codeBlocks = container.querySelectorAll('pre code');
            codeBlocks.forEach(block => {
                // Get the language from the class (e.g., "language-javascript")
                const langClass = Array.from(block.classList).find(cl => cl.startsWith('language-'));
                if (langClass) {
                    const lang = langClass.replace('language-', '');
                    if (window.Prism.languages[lang]) {
                        block.innerHTML = window.Prism.highlight(
                            block.textContent,
                            window.Prism.languages[lang],
                            lang
                        );
                    }
                }
            });
        }

        // Make content collapsible if needed
        this.makeContentCollapsible(container, content);
    }

    static preprocessOSeriesMarkdown(content) {
        // Ensure code blocks are properly formatted
        let processedContent = content;

        // Fix code blocks that might be missing language specification
        processedContent = processedContent.replace(/```\s*\n/g, '```plaintext\n');

        // Ensure proper spacing around code blocks
        processedContent = processedContent.replace(/\n*```/g, '\n\n```');

        // Fix list formatting
        processedContent = processedContent.replace(/(?<=\n)[-*+]\s/g, '\n- ');
        processedContent = processedContent.replace(/(?<=\n)\d+\.\s/g, '\n1. ');

        // Fix header formatting
        processedContent = processedContent.replace(/(?<=\n)#{1,6}\s/g, '\n$&');

        return processedContent;
    }

    static showTypingIndicator() {
        const template = this.templates.typingIndicator;
        if (!template) return;

        const chatBox = document.getElementById('chat-box');
        if (!chatBox) return;

        const indicator = template.content.cloneNode(true).firstElementChild;
        indicator.id = 'typing-indicator';
        chatBox.appendChild(indicator);
        chatBox.scrollTop = chatBox.scrollHeight;

        if (window.monitoring) {
            window.monitoring.mark('typingStart');
        }
    }

    static removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }

        if (window.monitoring) {
            window.monitoring.mark('typingEnd');
            window.monitoring.measure('typingDuration', 'typingStart', 'typingEnd');
        }
    }

    static showSuccess(message, durationMs = 3000) {
        if (window.showAlert) {
            window.showAlert(message, 'success', durationMs);
            return;
        }
        // Fallback if window.showAlert is undefined:
        console.log('SUCCESS:', message);
    }

    static showError(message, file = null) {
        if (message.includes('Authentication Error')) {
            message = message.replace('Authentication Error:', '🔑 Authentication Error:');
        }

        // Provide a clear prefix icon or emoji to errors
        message = `⚠️ ${message}`;

        let errorMessage = message;
        if (file) {
            errorMessage = `[${file.name}] ${message} (${(file.size / 1024 / 1024).toFixed(2)}MB)`;
        }

        if (window.showAlert) {
            window.showAlert(errorMessage, 'error', 10000);
        } else {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'pointer-events-auto fixed top-20 left-1/2 transform -translate-x-1/2 bg-red-100 dark:bg-red-900/50 text-red-900 dark:text-red-100 px-6 py-4 rounded-lg shadow-xl border-2 border-red-500/50 z-[2200] max-w-[90%] sm:max-w-lg';
            errorDiv.innerHTML = `
                <div class='flex items-center gap-3'>
                    <i class='fas fa-exclamation-circle text-lg'></i>
                    <p class='text-sm font-medium flex-1'>${errorMessage}</p>
                    <button onclick='this.parentElement.parentElement.remove()' class='hover:opacity-80 transition-opacity'>
                        <i class='fas fa-times'></i>
                    </button>
                </div>
            `;
            document.body.appendChild(errorDiv);
            setTimeout(() => {
                if (errorDiv.parentElement) {
                    errorDiv.remove();
                }
            }, 10000);
        }
    }

    static appendUserMessage(message, files = []) {
        if (!message || typeof message !== 'string') {
            window.monitoring?.logError('Invalid user message content.');
            return;
        }

        const chatBox = document.getElementById('chat-box');
        if (!chatBox) {
            window.monitoring?.logError('Chat box not found');
            return;
        }

        const messageDiv = this.renderUserMessage(message, files);
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    static async appendAssistantMessage(message, isStreaming = false, existingDiv = null, files = []) {
        console.log('[Response] Received model response:', message);
        if (!message) return;
        if (window.monitoring) {
            window.monitoring.log('debug', 'Appending assistant message:', message);
        }

        const chatBox = document.getElementById('chat-box');
        if (!chatBox) {
            window.monitoring?.logError('Chat box not found');
            return;
        }

        try {
            let messageDiv;

            if (!existingDiv) {
                messageDiv = this.renderAssistantMessage(message, isStreaming);
                chatBox.appendChild(messageDiv);
            } else {
                messageDiv = existingDiv;
                const content = typeof message === 'string' ? message : message.content;
                await this.finalizeAssistantMessage(messageDiv, content);
            }

            chatBox.scrollTop = chatBox.scrollHeight;
            return messageDiv;
        } catch (error) {
            window.monitoring?.logError('Error appending assistant message:', error);
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = `<p class='text-red-500'>Error creating message: ${error.message}</p>`;
            chatBox.appendChild(errorDiv);
        }
    }
}

// Export the MessageRenderer class
export { MessageRenderer };

// Also make globally accessible
window.MessageRenderer = MessageRenderer;

// Initialize after ChatConfig is ready
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Wait for ChatConfig to initialize first
        const config = ChatConfig.getInstance();
        await config.init();

        // Now initialize MessageRenderer
        await MessageRenderer.initialize();
    } catch (error) {
        console.error('Failed to initialize MessageRenderer:', error);
    }
});
