# PR Summary: fix/manager-long-output-line

## Summary

- The manager's turn failed when one line of its output passed 64 KB, which
  a single read of a large file does. Found asking the manager of a new
  project (Assay) to read its 71 KB specification.

## Scope

- `foreman/meta_agent.py`: the line limit of the stream the manager's
  output is read from.

## Files changed

- `foreman/meta_agent.py`, `tests/test_meta_agent.py`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A line of up to 64 MB is now held in memory while it is read.

## Tests

- ruff; `tests/test_meta_agent.py`, with a new test that runs a stand-in
  process printing a 300,000 character line; the full Python suite.

## Screenshots or output examples

- Before: `Meta-agent stream failed: Separator is not found, and chunk
  exceed the limit`.

## Acceptance criteria satisfied

- The same request to the Assay manager is answered.

## Follow-ups

- none
