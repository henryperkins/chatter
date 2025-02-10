'use strict';

class MessageRenderer {
    static templates = {
        assistant: null,
        user: null,
        attachment: null,
        attachmentItem: null
    };

    static initialize() {
        // Cache templates
        this.templates.assistant = document.getElementById('assistant-message-template');
        this.templates.user = document.getElementById('user-message-template');
        this.templates.attachment = document.getElementById('attachment-template');
        this.templates.attachmentItem = document.getElementById('attachment-item-template');

        if (!this.templates.assistant || !this.templates.user) {
            throw new Error('Message templates not found');
        }
    }

    static renderAssistantMessage(content, isStreaming = false) {
        const template = this.templates.assistant;
        const clone = template.content.cloneNode(true);
        const messageDiv = clone.querySelector('[data-role="assistant-message"]');
        const timestamp = clone.querySelector('span.text-xs');
        const regenerateButton = clone.querySelector('.regenerate-button');
        const copyButton = clone.querySelector('.copy-button');

        // Set content
        messageDiv.textContent = content;
        timestamp.textContent = new Date().toLocaleTimeString();
        copyButton.setAttribute('data-raw-content', content);

        // Hide regenerate button during streaming
        if (isStreaming && regenerateButton) {
            regenerateButton.style.display = 'none';
        }

        return clone.firstElementChild;
    }

    static renderUserMessage(content, files = []) {
        const template = this.templates.user;
        const clone = template.content.cloneNode(true);
        const messageText = clone.querySelector('p');
        const timestamp = clone.querySelector('span.text-xs');

        // Set content
        messageText.textContent = content;
        timestamp.textContent = new Date().toLocaleTimeString();

        // Add attachments if present
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

        files.forEach(file => {
            const itemTemplate = this.templates.attachmentItem;
            const itemClone = itemTemplate.content.cloneNode(true);
            
            const nameSpan = itemClone.querySelector('.attachment-name');
            nameSpan.textContent = file.name;

            const link = itemClone.querySelector('.attachment-link');
            if (file.url) {
                link.href = file.url;
            } else {
                link.remove();
            }

            attachmentList.appendChild(itemClone);
        });
window.MessageRenderer = MessageRenderer;

        return clone;
    }

    static finalizeAssistantMessage(messageDiv, content) {
        if (!messageDiv) return;

        const container = messageDiv.querySelector('[data-role="assistant-message"]');
        if (!container) return;

        // Render markdown and sanitize
        const renderedHtml = window.md.render(content);
        const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, {
            ALLOWED_TAGS: [
                'p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote',
                'a', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'br',
                'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del', 'input'
            ],
            ALLOWED_ATTRS: {
                a: ['href', 'title', 'target', 'rel', 'class'],
                span: ['class'],
                code: ['class'],
                pre: ['class'],
                div: ['class', 'style'],
                table: ['class'],
                th: ['class'],
                td: ['class'],
                input: ['type', 'checked', 'disabled'],
                li: ['class']
            },
            ADD_ATTR: ['target'],
            FORCE_BODY: true
        });

        container.innerHTML = sanitizedHtml;

        // Update raw content for copy button
        const copyButton = messageDiv.querySelector('.copy-button');
        if (copyButton) {
            copyButton.setAttribute('data-raw-content', content);
        }

        // Apply syntax highlighting
        if (window.Prism) {
            window.Prism.highlightAllUnder(container);
        }
    }
}
window.MessageRenderer = MessageRenderer;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    try {
        MessageRenderer.initialize();
    } catch (error) {
        console.error('Failed to initialize MessageRenderer:', error);
    }
});
