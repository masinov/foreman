"""Telling people what the engine did, on the policy they asked for.

An engine that runs unattended is only useful if it can reach the people who
are not attending it. Foreman decides *whether* to speak in the policy matrix,
which resolves a ``notification`` decision per task and stamps it on the events
worth announcing as a ``notify`` field:

``none``
    say nothing,
``attention``
    the moments that want a person -- engine attention turns and human gates,
``all``
    those, plus a task reaching done.

This module is the other half: where a project wants to be told, and how the
message actually gets there. Three pieces, each with one job.

:class:`NotificationDispatcher`
    Reads a persisted event, decides whether it is announceable, and writes a
    ``pending`` delivery row per destination. It runs inside the engine loop,
    so it does exactly one thing that can be slow -- a small indexed insert --
    and it never raises: a broken notification setup must not fail a task that
    otherwise succeeded.
:class:`NotificationDeliveryWorker`
    Drains due deliveries outside task execution, sends each through its
    transport, and either marks it delivered or schedules a retry with an
    exponential backoff. Exhausted retries leave a ``failed`` row carrying the
    last error, which is the only durable answer to "did anyone hear about
    that?".
:class:`WebhookTransport`
    The one transport that needs no credential beyond a URL. Adding chat or
    email means adding a class here and a row kind, not touching the engine.

The queue in the middle is the reason delivery cannot block a run. The engine
writes; something else sends; a destination that is down costs a row and a
retry rather than a stalled pass or a failed task.

The package is split by concern: ``policy`` (whether to speak),
``destinations`` (where), ``transport`` (how a message is sent) and
``delivery`` (the queue and the worker that drains it).
"""
