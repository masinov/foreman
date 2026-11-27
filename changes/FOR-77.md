A skipped branch update is recorded

- When a task's working copy has uncommitted changes, the update from the default branch is still skipped, but the skip is now recorded as an `engine.branch_sync` event (mode `refresh_skipped_dirty`) and the developer is told to save the work and merge the base.
