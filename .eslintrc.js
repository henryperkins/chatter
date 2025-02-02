module.exports = {
    env: {
        browser: true,
        es2021: true,
        node: true
    },
    extends: [
        'eslint:recommended',
        'plugin:import/recommended',
        'prettier'
    ],
    parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module'
    },
    rules: {
        'no-unused-vars': 'warn',
        'no-console': 'warn',
        'semi': ['error', 'always'],
        'quotes': ['error', 'single'],
        'import/no-unresolved': 'error',
        'import/named': 'error',
        'import/default': 'error',
        'import/namespace': 'error'
    },
    ignorePatterns: [
        'node_modules/',
        'dist/',
        '*.min.js',
        'static/css/output.css'
    ],
    settings: {
        'import/resolver': {
            node: {
                extensions: ['.js', '.jsx', '.ts', '.tsx']
            }
        }
    }
};
