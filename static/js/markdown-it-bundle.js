// Initialize markdown-it
const md = window.markdownit({
  html: true,
  linkify: true,
  typographer: true,
  highlight: function (str, lang) {
    if (lang && window.Prism && window.Prism.languages[lang]) {
      try {
        return window.Prism.highlight(str, window.Prism.languages[lang], lang);
      } catch (error) {
        console.error('Prism highlighting error:', error);
      }
    }
    return str; // return original string if no highlighting possible
  }
});

// Add plugin functionality directly
md.use((md) => {
  const highlight = md.options.highlight;
  md.options.highlight = (code, lang) => {
    if (!lang) return code;
    return highlight(code, lang);
  };
});

window.md = md;
