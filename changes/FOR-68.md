An ADR is numbered when it merges, and its index is generated

- A branch writes a decision as `docs/adr/new-<slug>.md` and refers to it by that path. When its task merges, Foreman renames it to `ADR-NNNN-<slug>.md` with the next free number, sets the number in its title line, rewrites the references to it and regenerates `docs/adr/README.md`. Two branches that each add a decision get different numbers.
- The numbering is in the merge commit, not a commit on the task's branch. The branch is not touched, so what lands is exactly what was tested and reviewed, and the number is chosen against the default branch as it is at that moment, so a merge that landed after the tests cannot take it.
- The index is generated from each ADR's title and status; the hand-written part above its marker line is kept.
- A merge that would leave two ADRs with the same number, from the branch or already on the default branch, is refused and the step's outcome names the files.
- The folder is the project setting `adr_dir` (default `docs/adr`; Settings › General). Empty, or a project without the folder, is left alone. `AGENTS.md`, the developer's prompt and `docs/adr/README.md` say how to add a decision.
