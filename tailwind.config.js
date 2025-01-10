module.exports = {
  content: [
    './templates/**/*.html',
    './src/**/*.js',
    './static/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        brandBlue: '#1E40AF',
        brandOrange: '#FF7F11',
      },
      spacing: {
        '128': '32rem',
      },
      screens: {
        '2xl': '1440px',
      },
    },
  },
  darkMode: 'class', // Ensure dark mode is enabled
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'), // For markdown/rich text
    require('@tailwindcss/aspect-ratio'), // For media containers
    require('@tailwindcss/line-clamp'), // For text truncation
  ],
};
