import fs from 'fs';

const dependencies = [
  {
    from: 'node_modules/axios/dist/axios.min.js',
    to: 'static/js/axios.min.js'
  },
  {
    from: 'node_modules/dompurify/dist/purify.min.js',
    to: 'static/js/dompurify.min.js'
  },
  {
    from: 'node_modules/markdown-it/dist/markdown-it.min.js',
    to: 'static/js/markdown-it.min.js'
  },
  {
    from: 'node_modules/prismjs/prism.js',
    to: 'static/js/prism.js'
  },
  {
    from: 'node_modules/markdown-it-prism/dist/markdownItPrism.min.js',
    to: 'static/js/markdown-it-prism.min.js'
  }
];

dependencies.forEach(dep => {
  try {
    const content = fs.readFileSync(dep.from);
    fs.writeFileSync(dep.to, content);
    console.log(`Copied ${dep.from} to ${dep.to}`);
  } catch (error) {
    console.error(`Error copying ${dep.from}:`, error.message);
  }
});
