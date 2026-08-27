"""Structured Audit Logger for GA & Keystone CMS MCP Server."""

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for holding the current request's user email
current_user_email: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_email", default="anonymous")

# Structured audit logger outputting to stdout for GCP Cloud Logging
audit_logger = logging.getLogger("mcp_audit")
audit_logger.setLevel(logging.INFO)

if not audit_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(handler)


def log_mcp_audit_event(
    target_service: str,
    tool_name: str,
    user_email: Optional[str] = None,
    user_role: Optional[str] = None,
    keystone_user_id: Optional[str] = None,
    cms_profile: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
    graphql_query: Optional[str] = None,
    graphql_variables: Optional[Dict[str, Any]] = None,
    status: str = "SUCCESS",
    error_message: Optional[str] = None
) -> None:
    """Emits a structured JSON audit log line to stdout for GCP Cloud Logging indexing."""
    email = user_email or current_user_email.get() or "anonymous"
    
    audit_entry = {
        "severity": "WARNING" if status == "ERROR" else "INFO",
        "event": "mcp_audit_log",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_email": email,
        "user_role": user_role or "unknown",
        "keystone_user_id": keystone_user_id or "unknown",
        "target_service": target_service,  # 'GA4' or 'KeystoneCMS'
        "cms_profile": cms_profile or "n/a",
        "tool_name": tool_name,
        "arguments": arguments or {},
        "graphql_query": graphql_query,
        "graphql_variables": graphql_variables,
        "status": status,
        "error_message": error_message
    }
    
    audit_logger.info(json.dumps(audit_entry, ensure_ascii=False))
