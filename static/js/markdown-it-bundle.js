// Initialize markdown-it with proper error handling
try {
    // Check for the actual markdown-it library
    if (typeof markdownit !== 'function') {
        throw new Error('markdown-it library not found');
    }

    const md = markdownit({
        html: true,
        linkify: true,
        typographer: true,
        highlight: function (str, lang) {
            // Default to javascript if language is not specified
            const language = lang || 'javascript';

            // Try to find the language in Prism
            let prismLang = window.Prism.languages[language];
            if (!prismLang) {
                // Try lowercase version
                prismLang = window.Prism.languages[language.toLowerCase()];
            }

            if (window.Prism && prismLang) {
                try {
                    const highlighted = window.Prism.highlight(str, prismLang, language);
                    // Add copy button and language indicator
                    return `<div class="code-block-wrapper relative">
                        <div class="code-language absolute right-2 top-2 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">${language}</div>
                        <button class="copy-code-button absolute right-2 top-8 p-1.5 rounded-md bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-300 transition-all duration-200" title="Copy code">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                            </svg>
                        </button>
                        <pre class="!mt-0 !mb-0"><code class="language-${language}">${highlighted}</code></pre>
                    </div>`;
                } catch (error) {
                    console.error('Prism highlighting error:', error);
                }
            }
            // Fallback with basic formatting
            return `<pre><code>${md.utils.escapeHtml(str)}</code></pre>`;
        }
    });

    // Add plugin functionality directly
    md.use((md) => {
        // Enhance code block rendering
        const defaultRender = md.renderer.rules.fence || function(tokens, idx, options, env, self) {
            return self.renderToken(tokens, idx, options);
        };

        md.renderer.rules.fence = function (tokens, idx, options, env, self) {
            const token = tokens[idx];
            const lang = token.info.trim();

            // Use the highlight function from options
            if (options.highlight) {
                const code = options.highlight(token.content, lang);
                if (code) {
                    return code;
                }
            }

            return defaultRender(tokens, idx, options, env, self);
        };

        // Add support for task lists
        md.renderer.rules.list_item_open = function (tokens, idx) {
            if (tokens[idx + 2] && tokens[idx + 2].content.startsWith('[ ] ')) {
                return '<li class="task-list-item"><input type="checkbox" disabled> ';
            }
            if (tokens[idx + 2] && tokens[idx + 2].content.startsWith('[x] ')) {
                return '<li class="task-list-item"><input type="checkbox" checked disabled> ';
            }
            return '<li>';
        };
    });

    // Add HTML entity decoding to markdown-it
    const originalRender = md.render.bind(md);
    md.render = function(src) {
        // First decode any HTML entities in the source
        const decodedSrc = src.replace(/&[#A-Za-z0-9]+;/g, match => {
            const textarea = document.createElement('textarea');
            textarea.innerHTML = match;
            return textarea.value;
        });
        return originalRender(decodedSrc);
    };

    // Add code block copy functionality
    document.addEventListener('click', (e) => {
        if (e.target.closest('.copy-code-button')) {
            const button = e.target.closest('.copy-code-button');
            const codeBlock = button.parentNode.querySelector('code');
            if (codeBlock) {
                const code = codeBlock.innerText;
                navigator.clipboard.writeText(code).then(() => {
                    // Show success state
                    const originalHTML = button.innerHTML;
                    button.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>';
                    button.classList.add('text-green-500');

                    // Reset after 2 seconds
                    setTimeout(() => {
                        button.innerHTML = originalHTML;
                        button.classList.remove('text-green-500');
                    }, 2000);
                }).catch(err => {
                    console.error('Failed to copy code:', err);
                    // Show error state
                    button.classList.add('text-red-500');
                    setTimeout(() => button.classList.remove('text-red-500'), 2000);
                });
            }
        }
    });

    window.md = md;
    window.he = { decode: function(text) { return md.render(text).replace(/<[^>]*>/g, ''); } };
} catch (error) {
    console.error('Failed to initialize markdown-it:', error);
    // Don't throw here - let the chat.js handle the error
}
