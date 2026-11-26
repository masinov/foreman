# Assay: the first outside project run through Foreman

Moved from `docs/STATUS.md` on 2026-11-26 (facts as of 2026-11-23).

- Assay (`../assay`) is the first outside project run through Foreman. Its
  sprints 1 and 2 are merged and completed. Its merges are approved by
  Foreman (`merge_approval=auto`, owner, 2026-11-20).
- Its `main` is pushed to its GitLab at `d64947e` (owner, 2026-11-23),
  sprints 1 and 2 included.
- Its tests write JUnit reports (unittest-xml-reporting), and its
  `test_command` is `python -m xmlrunner discover -s tests -o
  "$FOREMAN_TEST_REPORT_DIR"` (ADR-0035).
- Its engine (`foreman serve assay`) and its API (`192.168.50.107:8090`,
  `scripts/assay-api status`, from the Assay checkout) do not restart after a
  reboot. Both have been down since the reboot of 2026-11-23.
