"""Generic Keystone CMS GraphQL Client."""

import os
import urllib.request
import json
from typing import Any, Dict, Optional
from .config import CMSProfileConfig

_cached_session_cookies: Dict[str, str] = {}


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

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a GraphQL query/mutation against the Keystone CMS backend."""
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

        try:
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
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with {self.config.cms_name}: {str(e)}")
