/** @type {import('tailwindcss').Config} */
module.exports = {
  // 1. More specific content paths
  content: [
    './templates/**/*.{html,jinja2}',
    './static/js/**/*.{js,jsx}',
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
      }
    }
  },

  // 2. Disable unused core plugins
  corePlugins: {
    float: false,
    clear: false,
    container: false,
    objectFit: false,
    objectPosition: false,
    overscroll: false,
    placeholderColor: false,
    placeholderOpacity: false,
    ringOffsetColor: false,
    ringOffsetWidth: false,
    boxDecorationBreak: false,
    filter: false,
    backdropFilter: false,
    mixBlendMode: false,
    isolation: false,
    tableLayout: false,
  },

  // 3. Minimize variants
  variants: {
    extend: {
      backgroundColor: ['hover', 'focus', 'dark'],
      textColor: ['hover', 'focus', 'dark'],
      borderColor: ['hover', 'focus'],
      opacity: ['hover', 'disabled'],
      scale: ['hover', 'focus'],
    }
  },

  // 4. Configure typography plugin
  theme: {
    typography: {
      DEFAULT: {
        css: {
          maxWidth: '65ch',
          color: false,
          a: false,
          strong: false,
          blockquote: false,
          h1: false,
          h2: false,
          h3: false,
          h4: false,
          figure: false,
          'figure > *': false,
          figcaption: false,
          code: false,
          'pre code': false,
          'code::before': false,
          'code::after': false,
          'pre code::before': false,
          'pre code::after': false,
        }
      }
    }
  },

  darkMode: 'class',

  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ]
};
