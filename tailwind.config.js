module.exports = {
  content: [
    './templates/**/*.html',
    './static/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        brandBlue: '#1E40AF',
      },
      screens: {
        '2xl': '1440px',
      },
    },
  },
  darkMode: 'class',
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
  corePlugins: {
    // Disable unused core plugins
    float: false,
    clear: false,
    container: false,
  }
};
