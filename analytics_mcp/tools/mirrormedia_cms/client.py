"""Mirror Media CMS GraphQL Client."""

import os
import urllib.request
import json
from typing import Any, Dict, Optional

DEFAULT_CMS_ENDPOINT = "https://cms.mirrormedia.mg/api/graphql"


class MirrorMediaCMSClient:
    """Client for executing GraphQL queries against Mirror Media Keystone CMS."""

    def __init__(self, endpoint: Optional[str] = None, user_token: Optional[str] = None, session_cookie: Optional[str] = None):
        self.endpoint = endpoint or os.getenv("MIRRORMEDIA_GRAPHQL_ENDPOINT", DEFAULT_CMS_ENDPOINT)
        self.user_token = user_token
        self.session_cookie = session_cookie

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a GraphQL query/mutation against the Mirror Media CMS backend."""
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        if self.user_token:
            req.add_header("Authorization", f"Bearer {self.user_token}")
        if self.session_cookie:
            req.add_header("Cookie", f"keystonejs-session={self.session_cookie}")

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "errors" in result and result["errors"]:
                    error_msg = "; ".join(e.get("message", "Unknown GraphQL error") for e in result["errors"])
                    raise RuntimeError(f"CMS GraphQL Error: {error_msg}")
                return result.get("data", {})
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with Mirror Media CMS: {str(e)}")
