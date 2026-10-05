"""No-key checks for the first deployment checkpoint.
Calvin A. Prepetit
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from groq import RateLimitError
from streamlit.testing.v1 import AppTest

from advisor import MAX_HISTORY, new_session, process_turn


def fake_client(content="When does the noise happen?"):
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    return client


class AdvisorTests(unittest.TestCase):
    def test_original_wording_and_history(self):
        session = new_session()
        client = fake_client()
        original = "  my engin rattls??  "
        process_turn(original, session, lambda: client)
        process_turn("Only when cold", session, lambda: client)
        self.assertEqual(session["original_messages"][0], original)
        sent = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(sent[1]["content"], original)
        self.assertEqual(sent[-1]["content"], "Only when cold")

    def test_history_is_bounded(self):
        session = new_session()
        client = fake_client()
        for number in range(MAX_HISTORY + 2):
            process_turn(str(number), session, lambda: client)
        self.assertEqual(len(session["model_history"]), MAX_HISTORY * 2)
        self.assertEqual(len(session["original_messages"]), MAX_HISTORY + 2)

    def test_restart_and_cancel(self):
        for command in ("cancel", "restart", "start over"):
            session = new_session()
            process_turn("noise", session, fake_client)
            process_turn(command, session, fake_client)
            self.assertEqual(session, new_session())

    def test_failures_keep_original_without_raw_error(self):
        response = httpx.Response(429, request=httpx.Request("POST", "https://example.com"))
        errors = [RuntimeError("private provider details"), KeyError("GROQ_API_KEY"),
                  RateLimitError("private provider details", response=response, body=None)]
        for error in errors:
            session = new_session()
            client = fake_client()
            client.chat.completions.create.side_effect = error
            reply = process_turn("noise", session, lambda: client)
            self.assertNotIn("private provider details", reply)
            self.assertEqual(session["original_messages"], ["noise"])
            self.assertEqual(session["model_history"], [])
            if isinstance(error, RateLimitError):
                self.assertIn("rate limit", reply)

    def test_empty_and_malformed_responses(self):
        for content in (None, "", "   "):
            session = new_session()
            reply = process_turn("noise", session, lambda: fake_client(content))
            self.assertIn("could not complete", reply)
        client = fake_client()
        client.chat.completions.create.return_value.choices = []
        self.assertIn("could not complete", process_turn("noise", new_session(), lambda: client))

    def test_interface_opens_without_key(self):
        app = AppTest.from_file("app.py").run()
        self.assertFalse(app.exception)
        self.assertIn("automated software", app.caption[0].value)
        self.assertIn("Development preview", app.info[0].value)


if __name__ == "__main__":
    unittest.main()
