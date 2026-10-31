"""Structured Audit Logger for GA & Keystone CMS MCP Server."""

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

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


def summarize_response(data: Any, max_preview_len: int = 1000) -> Dict[str, Any]:
    """Generates an informative, security-safe summary of tool or GraphQL response for audit logging."""
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

        raw_repr = json.dumps(data, ensure_ascii=False, default=str)
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
