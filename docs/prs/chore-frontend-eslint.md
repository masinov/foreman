# chore/frontend-eslint

## Summary

The finish plan's Phase 4 names ESLint. It is in: a flat config with
`@eslint/js` recommended and the React and React Hooks rule sets, a `lint`
script that fails on any warning, and a step in CI's frontend job.

## Scope

- `frontend/eslint.config.js`, `frontend/package.json` (`lint`),
  `.github/workflows/ci.yml`.
- Seven unused imports removed (one in `App.jsx`, one in `TaskLayout.jsx`,
  five in tests) and one stale `eslint-disable` comment.

## Dependencies added, and why (ADR-0020, decision 4)

Development only: `eslint`, `@eslint/js`, `eslint-plugin-react`,
`eslint-plugin-react-hooks`, `globals`. The hooks rules catch what no test
here does: a hook called conditionally, a dependency missing from an effect.

## Rules turned off, and why

- `react/prop-types`: the frontend is plain JavaScript without prop types.
- `react/no-unescaped-entities`: an apostrophe in a sentence is not a bug.
- `React` may be imported and unused: files import it by habit and the
  automatic JSX runtime makes that harmless.

## Migrations

None.

## Tests

`npm --prefix frontend run lint` (clean), `npm --prefix frontend test`,
`npm --prefix frontend run build`.

## Follow-ups

After this merges, run `npm --prefix frontend ci` in any checkout that
shares its `node_modules`.
