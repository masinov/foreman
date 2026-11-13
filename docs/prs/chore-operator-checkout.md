# chore/operator-checkout

Not a change. It is the branch the operator's checkout sits on, so that
`main` can be held by the `_integration` worktree where merges land
(ADR-0012). It is fast-forwarded to `main` after each merge and never
carries commits of its own.
