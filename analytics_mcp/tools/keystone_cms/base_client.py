"""Generic Keystone CMS GraphQL Client with User Identity & Permission Resolution."""

import os
import urllib.request
import json
import time
from typing import Any, Dict, Optional, Tuple
from .config import CMSProfileConfig

_cached_session_cookies: Dict[str, str] = {}
_user_perm_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes cache for user permission lookups

# Role Definitions
ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"
ROLE_EDITOR = "editor"
ROLE_CONTRIBUTOR = "contributor"

ALLOWED_ROLES = {ROLE_ADMIN, ROLE_MODERATOR, ROLE_EDITOR, ROLE_CONTRIBUTOR}

# Fine-grained Tool-Level RBAC Permission Matrices
PUBLISH_ALLOWED_ROLES = {ROLE_ADMIN, ROLE_MODERATOR}
UPDATE_ALLOWED_ROLES = {ROLE_ADMIN, ROLE_MODERATOR, ROLE_EDITOR}
CREATE_ALLOWED_ROLES = {ROLE_ADMIN, ROLE_MODERATOR, ROLE_EDITOR, ROLE_CONTRIBUTOR}
READ_ALLOWED_ROLES = {ROLE_ADMIN, ROLE_MODERATOR, ROLE_EDITOR, ROLE_CONTRIBUTOR}


class KeystoneCMSBaseClient:
    """Base GraphQL client for interacting with Keystone 6 CMS backends."""

    def __init__(
        self,
        config: CMSProfileConfig,
        user_token: Optional[str] = None,
        session_cookie: Optional[str] = None
    ):
        self.config = config
        self.endpoint = config.graphql_endpoint
        self.user_token = user_token
        
        # Resolve auth environment variable overrides
        service_email_env = config.env_vars.get("service_email_env", "CMS_SERVICE_EMAIL")
        service_password_env = config.env_vars.get("service_password_env", "CMS_SERVICE_PASSWORD")
        cookie_env = config.env_vars.get("session_cookie_env", "CMS_SESSION_COOKIE")

        self.service_email = os.getenv(service_email_env) or os.getenv("CMS_SERVICE_EMAIL")
        self.service_password = os.getenv(service_password_env) or os.getenv("CMS_SERVICE_PASSWORD")

        profile_key = config.tool_prefix
        self.session_cookie = (
            session_cookie
            or (cookie_env and os.getenv(cookie_env))
            or os.getenv("CMS_SESSION_COOKIE")
            or _cached_session_cookies.get(profile_key)
        )

    def _ensure_authenticated(self) -> None:
        """Auto-authenticates using service account credentials if no session cookie exists."""
        profile_key = self.config.tool_prefix
        if self.session_cookie or self.user_token:
            return

        if not self.service_email or not self.service_password:
            return

        auth_query = """
        mutation Auth($email: String!, $password: String!) {
          authenticateUserWithPassword(email: $email, password: $password) {
            __typename
            ... on UserAuthenticationWithPasswordSuccess {
              sessionToken
              item { id email name role }
            }
            ... on UserAuthenticationWithPasswordFailure {
              message
            }
          }
        }
        """

        payload = json.dumps({
            "query": auth_query,
            "variables": {"email": self.service_email, "password": self.service_password}
        }).encode("utf-8")

        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                cookies = response.headers.get_all("Set-Cookie") or []
                for cookie_str in cookies:
                    if "keystonejs-session=" in cookie_str:
                        token_part = cookie_str.split("keystonejs-session=")[1].split(";")[0]
                        self.session_cookie = token_part
                        _cached_session_cookies[profile_key] = token_part
                        break
        except Exception:
            pass

    def _raw_execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a raw HTTP GraphQL request using the Service Account authentication."""
        self._ensure_authenticated()

        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        if self.user_token:
            req.add_header("Authorization", f"Bearer {self.user_token}")

        profile_key = self.config.tool_prefix
        cookie_header = self.session_cookie or _cached_session_cookies.get(profile_key)
        if cookie_header:
            req.add_header("Cookie", f"keystonejs-session={cookie_header}")

        with urllib.request.urlopen(req, timeout=15) as response:
            cookies = response.headers.get_all("Set-Cookie") or []
            for cookie_str in cookies:
                if "keystonejs-session=" in cookie_str:
                    token_part = cookie_str.split("keystonejs-session=")[1].split(";")[0]
                    self.session_cookie = token_part
                    _cached_session_cookies[profile_key] = token_part

            result = json.loads(response.read().decode("utf-8"))
            if "errors" in result and result["errors"]:
                error_msg = "; ".join(e.get("message", "Unknown GraphQL error") for e in result["errors"])
                raise RuntimeError(f"CMS GraphQL Error: {error_msg}")
            return result.get("data", {})

    def _verify_user_permission(self, email: str) -> Dict[str, Any]:
        """Verifies if the user email exists in Keystone CMS and possesses an allowed role."""
        if not email or email.lower() in ("anonymous", "none", ""):
            # Check if anonymous access is explicitly enabled (e.g. offline dev/testing)
            allow_anon = os.getenv("ALLOW_ANONYMOUS_ACCESS", "false").lower() in ("true", "1")
            if allow_anon:
                return {"id": "service_account", "role": ROLE_ADMIN, "name": "Local Service Account", "email": "anonymous"}
            raise PermissionError(
                "401 Unauthorized: Request does not contain an authenticated user identity (X-User-Email header missing). "
                "Please authenticate via Google Workspace SSO."
            )

        profile_key = self.config.tool_prefix
        cache_key = (email.lower(), profile_key)
        now = time.time()

        # Check cache
        if cache_key in _user_perm_cache:
            cached = _user_perm_cache[cache_key]
            if now - cached["timestamp"] < CACHE_TTL_SECONDS:
                return cached["info"]

        user_query = """
        query ResolveUser($email: String!) {
            users(where: { email: { equals: $email } }) {
                id
                email
                name
                role
            }
        }
        """

        data = self._raw_execute(user_query, {"email": email})
        users = data.get("users", [])

        if not users:
            raise PermissionError(
                f"403 Access Denied: User '{email}' is not registered in Keystone CMS ({self.config.cms_name}). "
                f"Please ensure your Google Workspace account has been granted access in CMS."
            )

        user_item = users[0]
        user_role = str(user_item.get("role", "")).lower()

        if user_role not in ALLOWED_ROLES:
            raise PermissionError(
                f"403 Access Denied: User '{email}' with role '{user_role}' is not authorized for CMS actions."
            )

        user_info = {
            "id": str(user_item.get("id")),
            "email": user_item.get("email"),
            "name": user_item.get("name"),
            "role": user_role
        }

        _user_perm_cache[cache_key] = {"timestamp": now, "info": user_info}
        return user_info

    def check_tool_permission(
        self,
        action: str,
        target_state: Optional[str] = None
    ) -> Dict[str, Any]:
        """Enforces fine-grained role-based access control (RBAC) on tool invocations.

        Rules:
        1. Action 'publish_post' or setting state to 'published'/'scheduled':
           Restricted exclusively to 'admin' and 'moderator'.
        2. Action 'update_post':
           Restricted to 'admin', 'moderator', and 'editor'.
           'contributor' is blocked from updating existing posts.
        3. Action 'create_post':
           'contributor' and 'editor' can only create posts in 'draft' state.
        4. Read actions:
           Accessible to all registered CMS roles.
        """
        from analytics_mcp.audit import current_user_email
        email = current_user_email.get() or "anonymous"
        user_info = self._verify_user_permission(email)
        user_role = user_info.get("role", "")

        # 1. Direct publish_post action
        if action == "publish_post":
            if user_role not in PUBLISH_ALLOWED_ROLES:
                raise PermissionError(
                    f"403 Access Denied: User '{email}' with role '{user_role}' is not authorized to publish posts. "
                    f"Publishing requires '{ROLE_ADMIN}' or '{ROLE_MODERATOR}' privileges."
                )

        # 2. Update post action & state escalation guard
        elif action == "update_post":
            if user_role not in UPDATE_ALLOWED_ROLES:
                raise PermissionError(
                    f"403 Access Denied: User '{email}' with role '{user_role}' is not authorized to update posts. "
                    f"Updating existing posts requires '{ROLE_EDITOR}', '{ROLE_MODERATOR}', or '{ROLE_ADMIN}'."
                )
            if target_state and target_state.lower() in ("published", "scheduled"):
                if user_role not in PUBLISH_ALLOWED_ROLES:
                    raise PermissionError(
                        f"403 Access Denied: User '{email}' with role '{user_role}' cannot change post state to '{target_state}'. "
                        f"Publishing or scheduling requires '{ROLE_ADMIN}' or '{ROLE_MODERATOR}' privileges."
                    )

        # 3. Create post action & state escalation guard
        elif action == "create_post":
            if user_role not in CREATE_ALLOWED_ROLES:
                raise PermissionError(
                    f"403 Access Denied: User '{email}' with role '{user_role}' is not authorized to create posts."
                )
            if target_state and target_state.lower() in ("published", "scheduled"):
                if user_role not in PUBLISH_ALLOWED_ROLES:
                    raise PermissionError(
                        f"403 Access Denied: User '{email}' with role '{user_role}' cannot directly create a post in '{target_state}' state. "
                        f"Creating published or scheduled posts requires '{ROLE_ADMIN}' or '{ROLE_MODERATOR}' privileges. "
                        f"Please submit as 'draft'."
                    )

        # 4. Read & search actions
        elif action in ("read", "list_recent_posts", "get_post", "search_posts", "filter_posts", "search_tags", "convert_to_draftjs", "get_my_profile"):
            if user_role not in READ_ALLOWED_ROLES:
                raise PermissionError(
                    f"403 Access Denied: User '{email}' with role '{user_role}' is not authorized to view CMS data."
                )

        return user_info

    def execute(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        action: Optional[str] = None,
        target_state: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes a GraphQL query/mutation after checking the user's Keystone permissions and RBAC matrix."""
        from analytics_mcp.audit import current_user_email, log_mcp_audit_event
        
        email = current_user_email.get() or "anonymous"
        user_info = None

        try:
            # Step 1: Verify User Identity and Fine-Grained Role Permissions
            if action:
                user_info = self.check_tool_permission(action, target_state=target_state)
            else:
                user_info = self._verify_user_permission(email)

            # Step 2: Execute GraphQL Query/Mutation
            result = self._raw_execute(query, variables)

            # Step 3: Audit Log Success Event
            log_mcp_audit_event(
                target_service="KeystoneCMS",
                tool_name=action or "graphql_execute",
                user_email=email,
                user_role=user_info.get("role") if user_info else None,
                keystone_user_id=user_info.get("id") if user_info else None,
                cms_profile=self.config.cms_name,
                graphql_query=query,
                graphql_variables=variables,
                status="SUCCESS"
            )
            return result

        except Exception as e:
            status_code = "FORBIDDEN" if isinstance(e, PermissionError) else "ERROR"
            log_mcp_audit_event(
                target_service="KeystoneCMS",
                tool_name=action or "graphql_execute",
                user_email=email,
                user_role=user_info.get("role") if user_info else None,
                keystone_user_id=user_info.get("id") if user_info else None,
                cms_profile=self.config.cms_name,
                graphql_query=query,
                graphql_variables=variables,
                status=status_code,
                error_message=str(e)
            )
            raise
