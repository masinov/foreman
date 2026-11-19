"""The project's manager (ADR-0022): an agent a person talks to, which
proposes and never changes anything by itself.

- ``agent``: one manager turn, its session and its history,
- ``proposals``: what the manager proposes and what confirming it applies,
- ``planning``: a sprint's plan or a task's split, asked of the manager,
- ``digest``: what the engine tells the manager when it needs attention.
"""
