# Assay serves any client; Foreman is its first

- `docs/directions/assay-and-foreman.md` records the owner's decision of 2026-11-27: nothing in Assay names Foreman or bends to it. Foreman reads Assay's public API, and anything more it needs is built on Foreman's side.
- Assay's S4 is shaped from its own specification (briefing with a snapshot id, bindings with the client's revision and that snapshot, findings any client reads).
