module.exports = {
  plugins: {
    'postcss-import': {},
    'postcss-nesting': {},
    'tailwindcss': {},
    'autoprefixer': {},
    'cssnano': process.env.NODE_ENV === 'production' ? {
      preset: ['default', {
        discardComments: {
          removeAll: true,
        },
      }]
    } : false
  }
};
