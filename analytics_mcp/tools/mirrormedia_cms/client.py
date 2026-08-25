"""Mirror Media CMS GraphQL Client."""

import os
import urllib.request
import urllib.parse
import json
from typing import Any, Dict, Optional

DEFAULT_CMS_ENDPOINT = "https://cms.mirrormedia.mg/api/graphql"

_cached_session_cookie: Optional[str] = None


class MirrorMediaCMSClient:
    """Client for executing GraphQL queries against Mirror Media Keystone CMS."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        user_token: Optional[str] = None,
        session_cookie: Optional[str] = None
    ):
        global _cached_session_cookie
        self.endpoint = endpoint or os.getenv("MIRRORMEDIA_GRAPHQL_ENDPOINT", DEFAULT_CMS_ENDPOINT)
        self.user_token = user_token or os.getenv("CMS_USER_TOKEN")
        self.session_cookie = (
            session_cookie
            or os.getenv("CMS_SESSION_COOKIE")
            or os.getenv("KEYSTONEJS_SESSION")
            or _cached_session_cookie
        )

    def _ensure_authenticated(self) -> None:
        """Auto-authenticates using CMS_SERVICE_EMAIL & CMS_SERVICE_PASSWORD if no session cookie exists."""
        global _cached_session_cookie
        if self.session_cookie or self.user_token:
            return

        service_email = os.getenv("CMS_SERVICE_EMAIL")
        service_password = os.getenv("CMS_SERVICE_PASSWORD")

        if not service_email or not service_password:
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
            "variables": {"email": service_email, "password": service_password}
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
                        _cached_session_cookie = token_part
                        break
        except Exception:
            pass

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a GraphQL query/mutation against the Mirror Media CMS backend."""
        global _cached_session_cookie
        self._ensure_authenticated()

        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        if self.user_token:
            req.add_header("Authorization", f"Bearer {self.user_token}")
        
        cookie_header = self.session_cookie or _cached_session_cookie
        if cookie_header:
            req.add_header("Cookie", f"keystonejs-session={cookie_header}")

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                cookies = response.headers.get_all("Set-Cookie") or []
                for cookie_str in cookies:
                    if "keystonejs-session=" in cookie_str:
                        token_part = cookie_str.split("keystonejs-session=")[1].split(";")[0]
                        self.session_cookie = token_part
                        _cached_session_cookie = token_part

                result = json.loads(response.read().decode("utf-8"))
                if "errors" in result and result["errors"]:
                    error_msg = "; ".join(e.get("message", "Unknown GraphQL error") for e in result["errors"])
                    raise RuntimeError(f"CMS GraphQL Error: {error_msg}")
                return result.get("data", {})
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with Mirror Media CMS: {str(e)}")
