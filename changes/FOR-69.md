# Foreman writes the status and sprint copies, and docs/prs is retired

- With the project setting `generate_copies` on (Settings › General › Advanced › Status and sprint copies; `foreman config <project> --set generate_copies=true`), Foreman writes `docs/STATUS.md` and `docs/sprints/current.md` from its database when a sprint starts and when it finishes (in the checkpoint's commit), and the finished sprint's archive copy, `docs/sprints/archive/sprint-<n>-<slug>.md`, from its record. `foreman copies <project> [--sprint <id>]` writes them by hand. `current.md` describes the active sprint (goal, tasks with keys, what each waits for, state) or says none is active and which comes next; `STATUS.md` names the last finished sprints, the active one, what is held or blocked, and the schema version.
- A merge commit's message is now `Merge <task key>: <title>` followed by the text of the branch's `changes/<task key>.md`.
- `docs/prs/` and its template are gone (git keeps them). `AGENTS.md`, the developer's and code reviewer's prompts, `README.md`, `docs/TESTING.md`, `docs/BRANCHING.md`, `docs/RELEASES.md` and `docs/ARCHITECTURE.md` no longer ask for a PR note or edits to the generated files; a conflict between spec, design and code is recorded in `docs/guide/conflicts-spec-design-code.md`. `scripts/validate_repo_memory.py` no longer requires `docs/prs/` or a PR note. New projects no longer get `write_pr_summaries` in their settings.
- What only the hand-written files held moved out first, nothing dropped:
  - STATUS.md "Documented conflicts between spec, mockup and code" to `docs/guide/conflicts-spec-design-code.md` (with two entries for this change);
  - "Running unattended" to `docs/guide/running-unattended.md`;
  - "Operating decisions" to `docs/guide/operating-decisions.md`;
  - "Validation baseline" to `docs/guide/validation-baseline.md`;
  - "What sprint 56 changed for an operator" and "Step facts from the repository" to `docs/guide/engine-behaviour-for-operators.md`;
  - the Assay, closing-by-hand, backend-layers and branches-and-checkout bullets of "Where the project is" to `docs/guide/assay-project.md`, `closing-a-task-by-hand.md`, `backend-layers.md` and `branches-and-the-operator-checkout.md`;
  - the rest of "Where the project is", as dated history, to `docs/checkpoints/status-history-through-2026-11-26.md`;
  - current.md's method, constraints and "Before the sprint / Before this sprint" for sprint 65 to `docs/checkpoints/sprint-65-opening.md` (its goal and tasks are in the database).
