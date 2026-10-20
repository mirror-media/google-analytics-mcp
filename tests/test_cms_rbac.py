"""Unit tests for Keystone CMS Role-Based Access Control (RBAC) & Security Safeguards."""

import os
import unittest
from unittest.mock import MagicMock, patch
from analytics_mcp.audit import current_user_email
from analytics_mcp.tools.keystone_cms.config import CMSProfileConfig
from analytics_mcp.tools.keystone_cms.adapter import KeystoneCMSAdapter
from analytics_mcp.tools.keystone_cms.base_client import (
    KeystoneCMSBaseClient,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_EDITOR,
    ROLE_CONTRIBUTOR,
    _user_perm_cache,
)


class TestKeystoneCMSRBAC(unittest.TestCase):
    def setUp(self):
        # Clear permissions cache before each test
        _user_perm_cache.clear()
        
        # Mock CMS Profile Config
        self.config = CMSProfileConfig({
            "cms_name": "Test Mirror Media CMS",
            "tool_prefix": "mm_",
            "graphql_endpoint": "http://mock-cms/api/graphql",
            "schema": {
                "post_list": "posts",
                "tag_list": "tags",
                "fields": {
                    "id": "id",
                    "title": "title",
                    "slug": "slug",
                    "state": "state",
                    "content": "content",
                },
                "relations": {}
            }
        })
        self.adapter = KeystoneCMSAdapter(self.config)

    def tearDown(self):
        _user_perm_cache.clear()
        current_user_email.set("anonymous")
        if "ALLOW_ANONYMOUS_ACCESS" in os.environ:
            del os.environ["ALLOW_ANONYMOUS_ACCESS"]

    def _mock_resolve_user(self, email: str, name: str, role: str):
        """Helper to mock Keystone user resolution GraphQL query."""
        def mock_raw_execute(query, variables=None):
            if "ResolveUser" in query:
                return {
                    "users": [
                        {"id": "usr_test_123", "email": email, "name": name, "role": role}
                    ]
                }
            if "CreatePost" in query:
                return {"createPost": {"id": "1", "slug": "test-slug", "title": "Test", "state": variables.get("data", {}).get("state", "draft")}}
            if "UpdatePost" in query:
                return {"updatePost": {"id": variables.get("id"), "slug": "test-slug", "title": "Test", "state": variables.get("data", {}).get("state", "draft")}}
            if "ListPosts" in query:
                return {"posts": [{"id": "1", "title": "Test Post", "slug": "test-post"}]}
            return {}
        return mock_raw_execute

    # --- 1. Anonymous Access Security Safeguard Tests ---

    def test_anonymous_access_denied_by_default(self):
        """Anonymous callers without X-User-Email must be rejected with 401."""
        current_user_email.set("anonymous")
        client = KeystoneCMSBaseClient(self.config)
        with self.assertRaises(PermissionError) as ctx:
            client.check_tool_permission("read")
        self.assertIn("401 Unauthorized", str(ctx.exception))
        self.assertIn("X-User-Email header missing", str(ctx.exception))

    def test_anonymous_access_allowed_when_explicitly_flagged(self):
        """When ALLOW_ANONYMOUS_ACCESS is true, fallback is permitted for local offline dev."""
        os.environ["ALLOW_ANONYMOUS_ACCESS"] = "true"
        current_user_email.set("anonymous")
        client = KeystoneCMSBaseClient(self.config)
        info = client.check_tool_permission("read")
        self.assertEqual(info["role"], ROLE_ADMIN)

    # --- 2. Admin Role Permissions Tests ---

    @patch.object(KeystoneCMSBaseClient, "_raw_execute")
    def test_admin_can_perform_all_actions(self, mock_exec):
        """Admin role has unrestricted access: read, create, update, publish."""
        email = "admin@mirrormedia.mg"
        current_user_email.set(email)
        mock_exec.side_effect = self._mock_resolve_user(email, "System Admin", ROLE_ADMIN)

        # Admin can publish
        res = self.adapter.publish_post(post_id="101")
        self.assertIsNotNone(res.get("post"))

        # Admin can update post directly to published
        res = self.adapter.update_post(post_id="101", state="published")
        self.assertIsNotNone(res.get("post"))

        # Admin can create post directly in published state
        res = self.adapter.create_post(title="Breaking", slug="breaking", content="News", state="published", auto_suggest=False)
        self.assertIsNotNone(res.get("post"))

        # Admin can read
        res = self.adapter.list_recent_posts()
        self.assertEqual(len(res.get("posts", [])), 1)

        # Profile check
        profile = self.adapter.get_my_profile()
        self.assertTrue(profile["permissions"]["can_publish"])
        self.assertTrue(profile["permissions"]["can_update_post"])

    # --- 3. Moderator Role Permissions Tests ---

    @patch.object(KeystoneCMSBaseClient, "_raw_execute")
    def test_moderator_can_publish_and_edit(self, mock_exec):
        """Moderator role can review, edit, and publish posts."""
        email = "moderator@mirrormedia.mg"
        current_user_email.set(email)
        mock_exec.side_effect = self._mock_resolve_user(email, "Section Chief", ROLE_MODERATOR)

        # Moderator can publish
        res = self.adapter.publish_post(post_id="102")
        self.assertIsNotNone(res.get("post"))

        # Moderator can create draft
        res = self.adapter.create_post(title="Draft", slug="draft", content="Draft", state="draft", auto_suggest=False)
        self.assertIsNotNone(res.get("post"))

        # Profile check
        profile = self.adapter.get_my_profile()
        self.assertTrue(profile["permissions"]["can_publish"])
        self.assertTrue(profile["permissions"]["can_update_post"])

    # --- 4. Editor Role Permissions Tests (Cannot Publish) ---

    @patch.object(KeystoneCMSBaseClient, "_raw_execute")
    def test_editor_can_create_and_update_drafts_but_cannot_publish(self, mock_exec):
        """Editor role can create and update drafts, but cannot publish or escalate state."""
        email = "editor@mirrormedia.mg"
        current_user_email.set(email)
        mock_exec.side_effect = self._mock_resolve_user(email, "Staff Reporter", ROLE_EDITOR)

        # 1. Editor CAN create a draft
        res = self.adapter.create_post(title="Draft Story", slug="draft-story", content="Content", state="draft", auto_suggest=False)
        self.assertIsNotNone(res.get("post"))

        # 2. Editor CAN update a post in draft state
        res = self.adapter.update_post(post_id="103", title="Updated Story", state="draft")
        self.assertIsNotNone(res.get("post"))

        # 3. Editor CANNOT call publish_post
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.publish_post(post_id="103")
        self.assertIn("403 Access Denied", str(ctx.exception))
        self.assertIn("not authorized to publish posts", str(ctx.exception))

        # 4. Editor CANNOT escalate state to published via update_post
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.update_post(post_id="103", state="published")
        self.assertIn("403 Access Denied", str(ctx.exception))
        self.assertIn("cannot change post state to 'published'", str(ctx.exception))

        # 5. Editor CANNOT escalate state to scheduled via update_post
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.update_post(post_id="103", state="scheduled")
        self.assertIn("403 Access Denied", str(ctx.exception))
        self.assertIn("cannot change post state to 'scheduled'", str(ctx.exception))

        # 6. Editor CANNOT directly create a published post
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.create_post(title="Story", slug="story", content="Content", state="published", auto_suggest=False)
        self.assertIn("403 Access Denied", str(ctx.exception))
        self.assertIn("cannot directly create a post in 'published' state", str(ctx.exception))

        # Profile check
        profile = self.adapter.get_my_profile()
        self.assertFalse(profile["permissions"]["can_publish"])
        self.assertTrue(profile["permissions"]["can_update_post"])
        self.assertTrue(profile["permissions"]["can_create_draft"])

    # --- 5. Contributor Role Permissions Tests (Draft Submission Only) ---

    @patch.object(KeystoneCMSBaseClient, "_raw_execute")
    def test_contributor_can_only_create_draft_and_read(self, mock_exec):
        """Contributor role can only submit new drafts and read; cannot update or publish."""
        email = "contributor@mirrormedia.mg"
        current_user_email.set(email)
        mock_exec.side_effect = self._mock_resolve_user(email, "Freelance Writer", ROLE_CONTRIBUTOR)

        # 1. Contributor CAN create draft
        res = self.adapter.create_post(title="Submission", slug="submission", content="Content", state="draft", auto_suggest=False)
        self.assertIsNotNone(res.get("post"))

        # 2. Contributor CANNOT create published post
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.create_post(title="Submission", slug="sub-pub", content="Content", state="published", auto_suggest=False)
        self.assertIn("403 Access Denied", str(ctx.exception))

        # 3. Contributor CANNOT update existing posts
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.update_post(post_id="104", title="New Title")
        self.assertIn("403 Access Denied", str(ctx.exception))
        self.assertIn("not authorized to update posts", str(ctx.exception))

        # 4. Contributor CANNOT publish
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.publish_post(post_id="104")
        self.assertIn("403 Access Denied", str(ctx.exception))

        # 5. Contributor CAN read
        res = self.adapter.list_recent_posts()
        self.assertEqual(len(res.get("posts", [])), 1)

        # Profile check
        profile = self.adapter.get_my_profile()
        self.assertFalse(profile["permissions"]["can_publish"])
        self.assertFalse(profile["permissions"]["can_update_post"])
        self.assertTrue(profile["permissions"]["can_create_draft"])

    # --- 6. Unregistered User Rejection Test ---

    @patch.object(KeystoneCMSBaseClient, "_raw_execute")
    def test_unregistered_user_rejected(self, mock_exec):
        """User email not present in Keystone CMS must be denied with 403."""
        email = "stranger@external.com"
        current_user_email.set(email)
        mock_exec.return_value = {"users": []}

        with self.assertRaises(PermissionError) as ctx:
            self.adapter.list_recent_posts()
        self.assertIn("403 Access Denied", str(ctx.exception))
        self.assertIn("is not registered in Keystone CMS", str(ctx.exception))

    # --- 7. Input Validation Security Safeguards ---

    @patch.object(KeystoneCMSBaseClient, "_raw_execute")
    def test_invalid_post_state_rejected(self, mock_exec):
        """Invalid state parameter must be caught immediately with ValueError."""
        email = "admin@mirrormedia.mg"
        current_user_email.set(email)
        mock_exec.side_effect = self._mock_resolve_user(email, "System Admin", ROLE_ADMIN)

        with self.assertRaises(ValueError) as ctx:
            self.adapter.create_post(title="Bad", slug="bad", content="Bad", state="malicious_state", auto_suggest=False)
        self.assertIn("Invalid post state", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            self.adapter.update_post(post_id="101", state="hacked")
        self.assertIn("Invalid post state", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
