"""``foreman task``: one module per kind of command.

- ``register``: the subcommands and their arguments,
- ``reads``: ``show`` and ``list``,
- ``changes``: ``add``, ``edit`` and ``override``,
- ``lifecycle``: ``accept``, ``block``, ``unblock``, ``done``, ``reopen``
  and ``cancel``.

Every change goes through ``foreman.mutations``, as the dashboard's do.
"""
