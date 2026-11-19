# PR Summary: refactor/remove-worker-fleet-role

## Summary

- Sprint 60, decision 3: the shipped role `developer_worker` ("Developer
  (worker fleet)") is removed. No workflow named it, no stored definition
  or run used it, and its only difference from `developer` was a commented
  `[agent.env]` example, which MANUAL §9 already gives.

## Tests

- role loading, prompt and CLI tests updated; full Python suite.
