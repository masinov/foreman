# feat/dashboard-sign-in

## Summary

A dashboard started with `--token` answered every request with 401 and the
rebuilt frontend showed that sentence on each page with no way to give the
token. Now the sign-in page takes the application's place.

## Scope

- `api/client.js`: the client announces a 401 (`onUnauthorized`); a request
  can present a token other than the stored one (`token` option), whose
  refusal is not announced.
- `app/SignInGate.jsx`: shows the application until a 401, then Sign in. The
  token is tried against `GET /session` and kept only if accepted. It also
  covers a token that stops being accepted while the dashboard is open.
- Sign out (user menu) already forgot the token; after it the gate asks again.

## Migrations

None. No API change.

## Risks

The token is kept in `localStorage`, as before this change.

## Tests

`frontend/src/app/App.test.jsx` (signing in), the whole frontend suite, the
Python suite, a look at the page against a server started with `--token`.

## Follow-ups

Items 7 to 10 of `docs/design/dashboard-v7/legacy-capabilities.md`.
