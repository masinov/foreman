import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

// What lint is for here: mistakes a test would not catch (a hook called
// conditionally, a dependency left out of an effect, a name that is never
// used). Formatting is not its job.
export default [
  { ignores: ["dist/**", "node_modules/**", "../foreman/dashboard_frontend_dist/**"] },
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser },
    },
    plugins: { react, "react-hooks": reactHooks },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // The build uses the automatic JSX runtime: React need not be in scope.
      ...react.configs["jsx-runtime"].rules,
      // Plain JavaScript without prop-types, by ADR-0020.
      "react/prop-types": "off",
      // An apostrophe in a sentence is a character, not a mistake.
      "react/no-unescaped-entities": "off",
      // Files import React by habit; with the automatic runtime that is harmless.
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^(_|React$)", caughtErrors: "none" }],
    },
  },
  {
    files: ["**/*.test.{js,jsx}", "vitest.setup.js", "src/testing/**"],
    languageOptions: { globals: { ...globals.browser, ...globals.node, ...globals.vitest } },
  },
  {
    files: ["*.config.js"],
    languageOptions: { globals: { ...globals.node } },
  },
];
