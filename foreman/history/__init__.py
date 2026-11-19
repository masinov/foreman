"""What happened, written once: the runs and events of the engine's work
(``records``) and their mirror in the process log (``logs``).

Every event saved here is logged as one JSON line and offered to the
notifier. The engine and the rules for a person's changes both write
through it, so it sits below both (ADR-0032).
"""
