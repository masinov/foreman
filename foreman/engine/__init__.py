"""The Foreman engine: what runs a task through its workflow.

``foreman.orchestrator.ForemanOrchestrator`` is the entry point. The modules
here hold the parts of it that stand on their own:

- ``errors`` and ``results``: what the engine raises and returns.
- ``limits``: validated settings, cost ceilings and time windows.
- ``model_selection``: which model a step runs on, and why.
- ``output_contract``: reading an agent's completion marker or decision.
- ``evidence``: the facts recorded about a task before it may merge.
"""
