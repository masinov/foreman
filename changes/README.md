# Change files

A change describes itself in its own file here, `changes/<task key>.md`
(a branch made by hand uses its branch name, slashes as dashes). Never edit
`CHANGELOG.md`: Foreman generates it.

The form is short: a title line, then a few bullets for a reader of the
changelog.

    # What changed, in a line

    - What a user or an operator sees now, and what they do.
    - The command, setting or file involved.

When a sprint finishes, Foreman folds the files into one section of
`CHANGELOG.md`, each change under its task key, and removes them in the
checkpoint's commit (ADR-0040). `foreman changelog <project>` does it by hand.
It runs for projects with `generate_changelog` on.
