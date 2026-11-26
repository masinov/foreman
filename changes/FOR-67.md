# A change writes its own change file, and Foreman generates CHANGELOG.md

- A task describes its change in `changes/<task key>.md` and never edits `CHANGELOG.md`; `AGENTS.md`, the developer's prompt, the code reviewer's prompt and `scripts/validate_repo_memory.py` say so.
- With the project setting `generate_changelog` on (Settings › General › Advanced › Changelog), finishing a sprint, by a user or by the engine, folds the change files into a new section at the top of `CHANGELOG.md` and removes them, in the checkpoint's commit. What the file held stays below the generated sections.
- A changelog that cannot be written is recorded as `engine.checkpoint_failed` with the reason; the sprint stays finished.
- `foreman changelog <project> [--sprint <id>]` writes it by hand.
