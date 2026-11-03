"""Structured Audit Logger for GA & Keystone CMS MCP Server."""

import contextlib
import contextvars
import ipaddress
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Mapping, Optional

# Context variables for holding the current request's user email and client IP
current_user_email: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_email", default="anonymous")
current_client_ip: contextvars.ContextVar[str] = contextvars.ContextVar("current_client_ip", default="unknown")

# Structured audit logger outputting to stdout for GCP Cloud Logging
audit_logger = logging.getLogger("mcp_audit")
audit_logger.setLevel(logging.INFO)

if not audit_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(handler)


def _first_header(scope: Mapping[str, Any], name: bytes) -> Optional[str]:
    """Returns the first value of a header, as Starlette's Headers.get does."""
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("utf-8", errors="replace")
    return None


def request_email_from_scope(scope: Mapping[str, Any]) -> str:
    return _first_header(scope, b"x-user-email") or "anonymous"


def request_ip_from_scope(scope: Mapping[str, Any]) -> str:
    """Returns the client IP, or "invalid" when the value is not an IP address.

    The gateway proxy replaces X-Forwarded-For with the client IP it derived,
    so the leftmost entry is that IP. A caller that reaches this service
    without the proxy can set the header to any value.
    """
    xff = _first_header(scope, b"x-forwarded-for")
    if xff:
        candidate = xff.split(",")[0].strip()
    else:
        client = scope.get("client")
        if not client:
            return "unknown"
        candidate = str(client[0])
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return "invalid"


@contextlib.contextmanager
def request_identity(scope: Optional[Mapping[str, Any]]) -> Iterator[None]:
    """Binds user email and client IP from the request carrying an MCP message.

    Over SSE, a tool call arrives in a POST /messages request but runs in the
    task of the GET /sse connection, so values set by the POST handler are not
    visible to the tool. Without a request scope (stdio), the current values
    are kept.
    """
    if scope is None:
        yield
        return
    token_email = current_user_email.set(request_email_from_scope(scope))
    token_ip = current_client_ip.set(request_ip_from_scope(scope))
    try:
        yield
    finally:
        current_user_email.reset(token_email)
        current_client_ip.reset(token_ip)


# Post body fields (Keystone brief/content/summary and Draft.js conversion
# output) can hold unpublished or member-only text, so they stay out of the
# preview.
PREVIEW_EXCLUDED_FIELDS = frozenset(
    {"brief", "content", "summary", "draftjs_json", "raw_state"}
)


def _without_preview_excluded_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: _without_preview_excluded_fields(v)
            for k, v in data.items()
            if k not in PREVIEW_EXCLUDED_FIELDS
        }
    if isinstance(data, list):
        return [_without_preview_excluded_fields(v) for v in data]
    return data


def summarize_response(data: Any, max_preview_len: int = 1000) -> Dict[str, Any]:
    """Generates a summary of a tool or GraphQL response for audit logging.

    The preview omits PREVIEW_EXCLUDED_FIELDS at any depth.
    """
    if data is None:
        return {"type": "none", "summary": "Empty response"}

    summary: Dict[str, Any] = {}
    try:
        if isinstance(data, list):
            summary["type"] = "list"
            summary["count"] = len(data)
            if len(data) > 0 and isinstance(data[0], dict):
                sample_ids = [item.get("id") or item.get("name") or item.get("slug") for item in data[:5] if isinstance(item, dict)]
                summary["sample_identifiers"] = [s for s in sample_ids if s]
        elif isinstance(data, dict):
            summary["type"] = "dict"
            summary["keys"] = list(data.keys())
            for k, v in data.items():
                if isinstance(v, list):
                    summary[f"{k}_count"] = len(v)
                    if len(v) > 0 and isinstance(v[0], dict):
                        sample_ids = [item.get("id") or item.get("title") or item.get("slug") or item.get("name") for item in v[:5] if isinstance(item, dict)]
                        summary[f"{k}_sample_identifiers"] = [s for s in sample_ids if s]
                elif isinstance(v, dict):
                    if "id" in v or "title" in v or "name" in v:
                        summary[f"{k}_info"] = {
                            "id": v.get("id"),
                            "title": v.get("title") or v.get("name"),
                            "state": v.get("state")
                        }
        else:
            summary["type"] = type(data).__name__

        raw_repr = json.dumps(
            _without_preview_excluded_fields(data),
            ensure_ascii=False,
            default=str,
        )
        if len(raw_repr) > max_preview_len:
            summary["preview"] = raw_repr[:max_preview_len] + "... [truncated]"
        else:
            summary["preview"] = raw_repr

    except Exception as e:
        summary["error"] = f"Failed to summarize response: {e}"

    return summary


def log_mcp_audit_event(
    target_service: str,
    tool_name: str,
    user_email: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_role: Optional[str] = None,
    keystone_user_id: Optional[str] = None,
    cms_profile: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
    graphql_query: Optional[str] = None,
    graphql_variables: Optional[Dict[str, Any]] = None,
    response_summary: Optional[Any] = None,
    status: str = "SUCCESS",
    error_message: Optional[str] = None
) -> None:
    """Emits a structured JSON audit log line to stdout for GCP Cloud Logging indexing."""
    email = user_email or current_user_email.get() or "anonymous"
    ip = client_ip or current_client_ip.get() or "unknown"
    
    audit_entry = {
        "severity": "WARNING" if status in ("ERROR", "FORBIDDEN") else "INFO",
        "event": "mcp_audit_log",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "client_ip": ip,
        "user_email": email,
        "user_role": user_role or "unknown",
        "keystone_user_id": keystone_user_id or "unknown",
        "target_service": target_service,  # 'GA4' or 'KeystoneCMS'
        "cms_profile": cms_profile or "n/a",
        "tool_name": tool_name,
        "arguments": arguments or {},
        "graphql_query": graphql_query,
        "graphql_variables": graphql_variables,
        "response_summary": response_summary,
        "status": status,
        "error_message": error_message
    }
    
    audit_logger.info(json.dumps(audit_entry, ensure_ascii=False))
