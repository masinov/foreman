# Changelog

All notable changes to this repository should be documented here.

The repo is still pre-implementation, so entries currently track bootstrap and
scaffold changes rather than product releases.

## [Unreleased]

### Added

- Foreman-specific repo instructions in `AGENTS.md`
- active sprint and backlog docs for the first Foreman implementation slice
- repository templates for PR summaries, checkpoints, and sprint archives
- `pyproject.toml` and the initial `foreman/` package scaffold
- a runnable CLI shell covering the spec-aligned command surface
- CLI smoke tests for `foreman --help`, `foreman projects`, and
  `foreman status`

### Changed

- repurposed the transplanted project-memory docs from Apparatus to Foreman
- aligned the autonomous wrapper scripts and repo validation expectations with
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- reset the roadmap, architecture baseline, and status docs to the actual
  Foreman project
- expanded repo validation to require the package scaffold and CLI smoke test
- enhanced `scripts/reviewed_codex.py` so approved slices no longer stop the
  run immediately; the supervisor now supports explicit full-spec completion,
  post-approval merge finalization, and continuation to the next slice
