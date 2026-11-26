# Releases and deployment, through existing CI/CD

- Date: 2026-11-18
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**Releases and deployment, through existing CI/CD.** Foreman does not
build or deploy. It decides when a version is cut, under a policy gate
such as merge approval. It starts the CI/CD pipeline (GitLab CI, GitHub
Actions, and so on), follows it, and shows its stages, artifacts and
environments on the sprint. It reacts to a failure. The same connector
reads CI checks on a task's branch, which is the pull-request
integration of Phase 5. A release can be code, an image or a trained
model; in each case Foreman records where it came from.
