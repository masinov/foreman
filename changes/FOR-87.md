# Migrations are a deploy step: the store no longer repairs the schema when it opens

- `foreman db migrate` is the only thing that changes the schema; migration 36 replaces the repair the store ran at every open.
- `foreman serve` and `foreman dashboard` refuse to start when the database's schema version is older or newer than the code's, with a message naming `foreman db migrate`.
- The MANUAL's database section gives the upgrade steps.
