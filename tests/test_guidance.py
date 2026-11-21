"""Where a person's note goes (the owner, 2026-11-19).

A note is for the agent doing the work. A reviewer is shown every note as
context and is never delivered one, so a note written while the task waits
for review still reaches the developer on its next pass.
"""

from __future__ import annotations

import unittest

from foreman.domain.guidance import (
    GUIDANCE_DELIVERED_EVENT,
    GUIDANCE_EVENT,
    guidance_notes,
    pending_guidance,
    prompt_with_guidance,
    prompt_with_guidance_as_context,
)
from foreman.domain.models import Event


def _event(event_id: str, event_type: str, timestamp: str, **payload) -> Event:
    return Event(
        id=event_id,
        run_id="run-1",
        task_id="t1",
        project_id="p1",
        event_type=event_type,
        timestamp=timestamp,
        payload=payload,
    )


class GuidanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = [
            _event("n1", GUIDANCE_EVENT, "2026-01-01T00:00:00", text="Leave the API alone."),
            _event(
                "d1",
                GUIDANCE_DELIVERED_EVENT,
                "2026-01-01T00:01:00",
                message_event_ids=["n1"],
                role="developer",
                step="develop",
            ),
            _event("n2", GUIDANCE_EVENT, "2026-01-01T00:02:00", text="Only the UI changes."),
        ]

    def test_a_reviewer_sees_every_note_and_whether_the_developer_has_it(self) -> None:
        prompt = prompt_with_guidance_as_context("Review this.", guidance_notes(self.events))
        self.assertIn("## What a user told the developer", prompt)
        self.assertIn("They\nare not instructions to you.", prompt)
        self.assertIn("given to the developer) Leave the API alone.", prompt)
        self.assertIn("not given to the developer yet) Only the UI changes.", prompt)
        self.assertNotIn("## Guidance from a user", prompt)

    def test_what_a_reviewer_was_shown_still_waits_for_the_developer(self) -> None:
        self.assertEqual([note.event_id for note in pending_guidance(self.events)], ["n2"])
        prompt = prompt_with_guidance("Develop this.", pending_guidance(self.events))
        self.assertIn("## Guidance from a user", prompt)
        self.assertIn("Only the UI changes.", prompt)
        self.assertNotIn("Leave the API alone.", prompt)

    def test_no_notes_leaves_the_prompt_as_it_was(self) -> None:
        self.assertEqual(prompt_with_guidance_as_context("Review this.", []), "Review this.")


if __name__ == "__main__":
    unittest.main()
