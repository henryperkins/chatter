/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './templates/*.html',
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
      zIndex: {
        'dropdown': '1000',
        'sticky': '1020',
        'fixed': '1030',
        'modal-backdrop': '1040',
        'modal': '1050',
        'popover': '1060',
        'tooltip': '1070',
      },
    },
  },
  darkMode: 'class',
  plugins: [
    (await import('@tailwindcss/forms')).default,
    (await import('@tailwindcss/typography')).default, // Ensure this plugin is included
  ],
  corePlugins: {
    // Disable unused core plugins
    float: false,
    clear: false,
    container: false,
  }
};
