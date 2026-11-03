"""Test cases for the audit module."""

import json
import unittest

from analytics_mcp.audit import (
    request_email_from_scope,
    request_ip_from_scope,
    summarize_response,
)

BODY_TEXT = "body text that must not be logged"


def _draft(post_id):
    return {
        "id": post_id,
        "slug": f"draft-{post_id}",
        "title": f"Draft {post_id}",
        "state": "draft",
        "isMember": True,
        "brief": json.dumps({"blocks": [{"text": BODY_TEXT}]}),
        "content": json.dumps({"blocks": [{"text": BODY_TEXT}]}),
        "summary": BODY_TEXT,
    }


class SummarizeResponseTest(unittest.TestCase):
    def test_preview_omits_body_fields_of_single_post(self):
        summary = summarize_response({"post": _draft("9")})

        self.assertNotIn(BODY_TEXT, summary["preview"])
        self.assertEqual(
            summary["post_info"],
            {"id": "9", "title": "Draft 9", "state": "draft"},
        )
        preview = json.loads(summary["preview"])
        self.assertEqual(
            preview,
            {
                "post": {
                    "id": "9",
                    "slug": "draft-9",
                    "title": "Draft 9",
                    "state": "draft",
                    "isMember": True,
                }
            },
        )

    def test_preview_omits_body_fields_in_lists(self):
        summary = summarize_response({"posts": [_draft("1"), _draft("2")]})

        self.assertNotIn(BODY_TEXT, summary["preview"])
        self.assertEqual(summary["posts_count"], 2)
        self.assertEqual(summary["posts_sample_identifiers"], ["1", "2"])
        self.assertIn("Draft 2", summary["preview"])

    def test_preview_omits_draftjs_conversion_output(self):
        raw_state = {"blocks": [{"text": BODY_TEXT}], "entityMap": {}}
        summary = summarize_response(
            {"draftjs_json": json.dumps(raw_state), "raw_state": raw_state}
        )

        self.assertNotIn(BODY_TEXT, summary["preview"])
        self.assertEqual(summary["keys"], ["draftjs_json", "raw_state"])

    def test_preview_keeps_other_fields(self):
        data = [{"name": "accountSummaries/1", "displayName": "fake"}]
        summary = summarize_response(data)

        self.assertEqual(json.loads(summary["preview"]), data)
        self.assertEqual(summary["sample_identifiers"], ["accountSummaries/1"])


def _scope(*headers, client=("192.0.2.1", 1234)):
    return {
        "type": "http",
        "headers": [(k.encode(), v.encode()) for k, v in headers],
        "client": client,
    }


class RequestIdentityFromScopeTest(unittest.TestCase):
    def test_ip_is_leftmost_forwarded_for_entry(self):
        scope = _scope(
            ("x-forwarded-for", "203.0.113.9, 192.0.2.50, 192.0.2.60")
        )
        self.assertEqual(request_ip_from_scope(scope), "203.0.113.9")

    def test_ip_uses_first_header_line(self):
        scope = _scope(
            ("x-forwarded-for", "203.0.113.9"),
            ("x-forwarded-for", "198.51.100.7"),
        )
        self.assertEqual(request_ip_from_scope(scope), "203.0.113.9")

    def test_ip_that_is_not_an_address_is_invalid(self):
        for value in ("not-an-ip", "203.0.113.9 extra", ", 203.0.113.9"):
            with self.subTest(value=value):
                scope = _scope(("x-forwarded-for", value))
                self.assertEqual(request_ip_from_scope(scope), "invalid")

    def test_ip_is_normalized(self):
        scope = _scope(("x-forwarded-for", "2001:DB8::1"))
        self.assertEqual(request_ip_from_scope(scope), "2001:db8::1")

    def test_ip_falls_back_to_connection_address(self):
        self.assertEqual(request_ip_from_scope(_scope()), "192.0.2.1")
        self.assertEqual(request_ip_from_scope(_scope(client=None)), "unknown")

    def test_email_uses_first_header_line(self):
        scope = _scope(
            ("x-user-email", "a@example.test"),
            ("x-user-email", "b@example.test"),
        )
        self.assertEqual(request_email_from_scope(scope), "a@example.test")
        self.assertEqual(request_email_from_scope(_scope()), "anonymous")


if __name__ == "__main__":
    unittest.main()
