import js from '@eslint/js';
import ts from 'typescript-eslint';
export default ts.config(js.configs.recommended, ...ts.configs.recommended, {
  files: ['**/*.ts'],
  languageOptions: { globals: { window:'readonly', document:'readonly', fetch:'readonly', console:'readonly', localStorage:'readonly', indexedDB:'readonly', URL:'readonly', URLSearchParams:'readonly', HTMLElement:'readonly', HTMLInputElement:'readonly', HTMLSelectElement:'readonly', HTMLButtonElement:'readonly', setTimeout:'readonly', clearTimeout:'readonly', process:'readonly' } },
});
