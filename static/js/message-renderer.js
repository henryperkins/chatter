'use strict';

class MessageRenderer {
    static templates = {
        assistant: null,
        user: null,
        attachment: null,
        attachmentItem: null
    };

    static initialize() {
        // Cache templates from the DOM
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
        const messageContent = clone.querySelector('[data-role="assistant-message"]');
        const proseDiv = messageContent.querySelector('.prose');
        const timestamp = clone.querySelector('span.text-xs');
        const regenerateButton = clone.querySelector('.regenerate-button');
        const copyButton = clone.querySelector('.copy-button');

        // Set content (plaintext by default—will be replaced in finalize)
        proseDiv.textContent = content;

        // Show a timestamp
        timestamp.textContent = new Date().toLocaleTimeString();

        // If there's a copy button, store raw text. 
        if (copyButton) {
            copyButton.setAttribute('data-raw-content', content);
        }

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

        // Assign user content
        messageText.textContent = content;
        timestamp.textContent = new Date().toLocaleTimeString();

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

        // Check if content is long enough to need collapsing
        const shouldCollapse = content.length > 500 || 
                             content.split('\n').length > 10 ||
                             container.clientHeight > 300;

        if (shouldCollapse) {
            messageContent.classList.add('collapsed');
            toggleButton.classList.remove('hidden');
            
            toggleButton.addEventListener('click', () => {
                messageContent.classList.toggle('collapsed');
                toggleButton.textContent = messageContent.classList.contains('collapsed') 
                    ? 'Show more' 
                    : 'Show less';
            });
        }
    }

    static finalizeAssistantMessage(messageDiv, content) {
        if (!messageDiv) return;

        const container = messageDiv.querySelector('.prose');
        if (!container) return;

        // Render markdown
        const renderedHtml = window.md ? window.md.render(content) : content;
        // Sanitize with DOMPurify
        const sanitizedHtml = window.DOMPurify
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
            })
          : renderedHtml; // fallback if no DOMPurify

        // Insert sanitized HTML
        container.innerHTML = sanitizedHtml;

        // Update the copy button’s data-raw-content
        const copyButton = messageDiv.querySelector('.copy-button');
        if (copyButton) {
            copyButton.setAttribute('data-raw-content', content);
        }

        // Syntax highlighting
        if (window.Prism) {
            window.Prism.highlightAllUnder(container);
        }

        // Make content collapsible if needed
        this.makeContentCollapsible(container, content);
    }
}

// Make the renderer globally accessible if you want:
window.MessageRenderer = MessageRenderer;

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    try {
        MessageRenderer.initialize();
    } catch (error) {
        console.error('Failed to initialize MessageRenderer:', error);
    }
});