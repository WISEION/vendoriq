import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'playwright-report', 'test-results', 'preview'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      // Gate 2 of the build brief: no business logic in the frontend. Scoring and matching
      // live in packages/scoring and are reached only through the API.
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/scoring/**', '**/matching/**', 'vendoriq_scoring*', '@vendoriq/scoring*'],
              message:
                'Scoring and matching are server-side (packages/scoring). Call the API instead.',
            },
          ],
        },
      ],
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
);
