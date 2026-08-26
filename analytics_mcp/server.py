#!/usr/bin/env python

# Copyright 2025 Google LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Entry point for the Google Analytics & Mirror Media CMS Unified MCP server."""

import asyncio
import os
import sys
import traceback
import analytics_mcp.coordinator as coordinator
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

try:
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    HAS_HTTP_DEPS = True
except ImportError:
    HAS_HTTP_DEPS = False


async def handle_healthz(request):
    return JSONResponse({"status": "ok", "server": coordinator.app.name})


if HAS_HTTP_DEPS:
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        email = request.headers.get("x-user-email") or request.headers.get("X-User-Email") or "anonymous"
        from analytics_mcp.audit import current_user_email
        current_user_email.set(email)

        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await coordinator.app.run(
                streams[0],
                streams[1],
                InitializationOptions(
                    server_name=coordinator.app.name,
                    server_version="1.0.0",
                    capabilities=coordinator.app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    async def handle_messages(request):
        email = request.headers.get("x-user-email") or request.headers.get("X-User-Email") or "anonymous"
        from analytics_mcp.audit import current_user_email
        current_user_email.set(email)

        await sse.handle_post_message(request.scope, request.receive, request._send)

    starlette_app = Starlette(
        routes=[
            Route("/debug/healthz", handle_healthz),
            Route("/healthz", handle_healthz),
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ]
    )


async def run_server_async():
    """Runs the MCP server over HTTP SSE (default for Cloud Run) or Stdio (if --stdio flag is passed)."""
    if "--stdio" in sys.argv or not HAS_HTTP_DEPS:
        print("Starting MCP Stdio Server:", coordinator.app.name, file=sys.stderr)
        import mcp.server.stdio
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await coordinator.app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=coordinator.app.name,
                    server_version="1.0.0",
                    capabilities=coordinator.app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    else:
        port = int(os.getenv("PORT", "8080"))
        print(f"Starting MCP HTTP SSE Server on port {port}: {coordinator.app.name}", file=sys.stderr)
        config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


def run_server():
    """Synchronous wrapper to run the async MCP server."""
    asyncio.run(run_server_async())


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nMCP Server stopped by user.", file=sys.stderr)
    except Exception:
        print("MCP Server encountered an error:", file=sys.stderr)
        traceback.print_exc()
    finally:
        print("MCP Server process exiting.", file=sys.stderr)
