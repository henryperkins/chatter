/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './templates/**/*.jinja2',
    './static/js/**/*.js',
    './static/css/**/*.css', // Ensure this path includes your input.css
  ],
  theme: {
    extend: {
      colors: {
        brandBlue: '#1E40AF',
      },
      spacing: {
        '44': '11rem', // For pb-44 class
        '32': '8rem',  // For pb-32 class
      },
      screens: {
        '2xl': '1440px', // Custom 2xl breakpoint
      },
      translate: {
        '-full': '-100%', // Custom translate value
      },
      zIndex: {
        dropdown: '1000',
        sticky: '1020',
        fixed: '1030',
        'modal-backdrop': '1040',
        modal: '1050',
        popover: '1060',
        tooltip: '1070',
      },
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
          },
        },
      },
      // Extend variants under theme.extend
      backgroundColor: ['dark'],
      textColor: ['dark'],
      opacity: ['disabled'],
      scale: ['hover', 'focus'],
      display: ['group-hover'],
      transform: ['hover', 'focus'],
    },
  },
  corePlugins: {
    float: false,
    clear: false,
    overscrollBehavior: false,
    boxDecorationBreak: false,
    mixBlendMode: false,
    isolation: false,
    tableLayout: false,
    // 'transform' is enabled by default
  },
  darkMode: 'class',
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
