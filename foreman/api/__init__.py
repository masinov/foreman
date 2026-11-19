"""The dashboard's HTTP API.

``app`` builds the FastAPI application: authentication and browser-origin
middleware, the error envelope, the frontend shell, and the routers.
``routers`` has one module of routes per resource. ``context`` is what a
router needs from the application it is mounted on.

Every route is served under ``/api/v1``. The same routes also answer under
``/api``, the path the first release used, until clients have moved.
"""
