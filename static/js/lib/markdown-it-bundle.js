// Initialize markdown-it with proper error handling
try {
    // Check for the actual markdown-it library
    if (typeof markdownit !== 'function') {
        throw new Error('markdown-it library not found');
    }

    const md = window.markdownit({
        html: true,
        linkify: true,
        breaks: true,  // Enable line breaks
        typographer: true,  // Enable smart quotes and other typographic replacements
        highlight: function (str, lang) {
            // Use the specified language or default to 'plaintext'
            const language = lang && Prism.languages[lang] ? lang : 'plaintext';
            const className = 'language-' + language;

            try {
                // Clean up the code string
                str = str.replace(/^\n+|\n+$/g, '');  // Remove extra newlines
                const highlighted = Prism.highlight(str, Prism.languages[language], language);
                
                // Add copy button and wrap in container
                return `
                    <div class="code-block-wrapper relative group">
                        <button class="copy-code-button absolute right-2 top-2 p-2 rounded-lg bg-gray-800/50 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                            </svg>
                        </button>
                        <pre class="${className} overflow-x-auto"><code class="${className}">${highlighted}</code></pre>
                    </div>`;
            } catch (__) {
                // Fallback for unknown languages
                return `
                    <div class="code-block-wrapper relative group">
                        <button class="copy-code-button absolute right-2 top-2 p-2 rounded-lg bg-gray-800/50 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                            </svg>
                        </button>
                        <pre class="${className} overflow-x-auto"><code class="${className}">${md.utils.escapeHtml(str)}</code></pre>
                    </div>`;
            }
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

        // Enhanced list handling
        const defaultListRender = md.renderer.rules.list_item_open || function(tokens, idx, options, env, self) {
            return self.renderToken(tokens, idx, options);
        };

        md.renderer.rules.list_item_open = function (tokens, idx) {
            const token = tokens[idx];
            
            // Handle task lists
            if (tokens[idx + 2] && tokens[idx + 2].content.startsWith('[ ] ')) {
                return '<li class="task-list-item"><input type="checkbox" disabled> ';
            }
            if (tokens[idx + 2] && tokens[idx + 2].content.startsWith('[x] ')) {
                return '<li class="task-list-item"><input type="checkbox" checked disabled> ';
            }

            // Add proper nesting classes
            let classes = ['list-item'];
            let nesting = 0;
            for (let i = idx - 1; i >= 0; i--) {
                if (tokens[i].type === 'bullet_list_open') nesting++;
            }
            if (nesting > 0) {
                classes.push(`nested-${nesting}`);
            }

            return `<li class="${classes.join(' ')}">`;
        };

        // Enhance table rendering
        md.renderer.rules.table_open = function() {
            return '<div class="table-wrapper"><table>';
        };
        
        md.renderer.rules.table_close = function() {
            return '</table></div>';
        };

        // Add horizontal rule styling
        md.renderer.rules.hr = function() {
            return '<hr class="markdown-hr">';
        };
    });

    // Add HTML entity decoding to markdown-it
    const originalRender = md.render.bind(md);
    md.render = function(src) {
        if (!src) return '';
        
        // Clean up the source text
        src = src.replace(/\n{3,}/g, '\n\n');  // Replace multiple newlines with double newlines
        
        // First decode any HTML entities in the source
        const decodedSrc = src.replace(/&[#A-Za-z0-9]+;/g, match => {
            const textarea = document.createElement('textarea');
            textarea.innerHTML = match;
            return textarea.value;
        });
        
        // Render and enhance the output
        let html = originalRender(decodedSrc);
        
        // Add proper spacing around elements
        html = html.replace(/<\/pre>\s*<pre/g, '</pre>\n<pre');  // Add newline between code blocks
        html = html.replace(/<\/h([1-6])>\s*<p/g, '</h$1>\n<p');  // Add newline after headers
        html = html.replace(/<\/table>\s*<p/g, '</table>\n<p');   // Add newline after tables
        html = html.replace(/<\/blockquote>\s*<p/g, '</blockquote>\n<p'); // Add newline after blockquotes
        
        return html;
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
    window.he = { decode: function(text) { 
        if (!text) return '';
        const textarea = document.createElement('textarea');
        textarea.innerHTML = text;
        return textarea.value;
    }};
} catch (error) {
    console.error('Failed to initialize markdown-it:', error);
    // Don't throw here - let the chat.js handle the error
}
