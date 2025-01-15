/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './templates/**/*.jinja2',
    './static/js/**/*.js',
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
      // Add typography configuration here instead of duplicate theme
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
    }
  },

  corePlugins: {
    float: false,
    clear: false,
    overscroll: false,
    boxDecorationBreak: false,
    mixBlendMode: false,
    isolation: false,
    tableLayout: false,
    transform: true,
  },

  variants: {
    extend: {
      backgroundColor: ['hover', 'focus', 'dark'],
      textColor: ['hover', 'focus', 'dark'],
      borderColor: ['hover', 'focus'],
      opacity: ['hover', 'disabled'],
      scale: ['hover', 'focus'],
    }
  },

  darkMode: 'class',

  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ]
};
