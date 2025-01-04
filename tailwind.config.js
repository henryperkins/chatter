/** @type {import('tailwindcss').Config} */
module.exports = {
  // 1. Specify all files Tailwind should scan for class names.
  //    This ensures Tailwind can tree-shake (remove) unused classes in production.
  //    You can add JS, TS, HTML, Jinja2, etc., depending on your stack.
  content: [
    './templates/**/*.html',   // If you're using Flask or Django templates
    './src/**/*.js',           // If you're using React, Vue, or vanilla JS
    './static/**/*.js',        // If you have separate JS in a 'static' folder
    // './**/*.html',           // Or a more general glob for an entire directory
  ],

  // 2. Extend or override Tailwind’s default theme.
  theme: {
    extend: {
      // Example: define custom colors
      colors: {
        brandBlue: '#1E40AF',
        brandOrange: '#FF7F11',
      },
      // Example: custom spacing
      spacing: {
        '128': '32rem',
      },
      // Example: custom breakpoints
      screens: {
        '2xl': '1440px',
      },
      // etc.
    },
  },

  // 3. Enable dark mode, if desired. Options:
  //    'class' (manually add "dark" class to <html>), or 'media' (prefers-color-scheme).
  darkMode: 'class',

  // 4. Add official or community plugins if you need them.
  //    E.g. forms plugin, typography plugin, line-clamp, aspect-ratio, etc.
  plugins: [
    // require('@tailwindcss/forms'),
    // require('@tailwindcss/typography'),
    // require('@tailwindcss/aspect-ratio'),
  ],
};