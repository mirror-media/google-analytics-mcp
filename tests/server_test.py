import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

import analytics_mcp.coordinator as coordinator
import analytics_mcp.server as server
from analytics_mcp.audit import current_client_ip, current_user_email
from analytics_mcp.server import HAS_HTTP_DEPS, starlette_app

FAKE_TOOL = "get_account_summaries"


class FakeTool:
    name = FAKE_TOOL

    async def run_async(self, args, tool_context):
        return [{"name": "accountSummaries/1", "displayName": "fake"}]


def _audit_events(logs):
    return [json.loads(record.getMessage()) for record in logs.records]


@unittest.skipUnless(HAS_HTTP_DEPS, "HTTP MCP dependencies are not installed")
class HTTPTransportTest(unittest.IsolatedAsyncioTestCase):
    async def test_streamable_http_initialize(self):
        transport = httpx.ASGITransport(app=starlette_app)
        async with starlette_app.router.lifespan_context(starlette_app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    "/mcp",
                    headers={"Accept": "application/json, text/event-stream"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "test-client",
                                "version": "1.0",
                            },
                        },
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.history, [])
        self.assertEqual(
            response.json()["result"]["serverInfo"]["name"],
            "Google Analytics & Mirror Media CMS Unified MCP Server",
        )

    def test_legacy_sse_routes_remain_available(self):
        paths = {route.path for route in starlette_app.routes}
        self.assertIn("/sse", paths)
        self.assertIn("/messages", paths)
        self.assertIn("/mcp", paths)


@unittest.skipUnless(HAS_HTTP_DEPS, "HTTP MCP dependencies are not installed")
class SSEAuditIdentityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import uvicorn

        # The Streamable HTTP session manager runs only once per process, and
        # HTTPTransportTest already starts it; SSE does not need it.
        config = uvicorn.Config(
            starlette_app,
            host="127.0.0.1",
            port=0,
            lifespan="off",
            log_level="critical",
        )
        self.server = uvicorn.Server(config)
        self.server_task = asyncio.create_task(self.server.serve())
        while not self.server.started:
            await asyncio.sleep(0.01)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"

    async def asyncTearDown(self):
        self.server.should_exit = True
        self.server.force_exit = True
        await asyncio.wait_for(self.server_task, 5)

    async def _call_tool_over_sse(self, sse_headers, post_headers):
        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": FAKE_TOOL, "arguments": {}},
        }
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=10, trust_env=False
        ) as client:
            async with client.stream(
                "GET", "/sse", headers=sse_headers
            ) as stream:
                lines = stream.aiter_lines()

                async def next_data():
                    async for line in lines:
                        if line.startswith("data:"):
                            return line.split(":", 1)[1].strip()

                endpoint = await next_data()
                await client.post(
                    endpoint, headers=post_headers, json=initialize
                )
                await next_data()
                await client.post(
                    endpoint,
                    headers=post_headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                )
                await client.post(endpoint, headers=post_headers, json=call)
                return await next_data()

    async def test_tool_call_audit_uses_post_request_identity(self):
        with patch.dict(coordinator.tool_map, {FAKE_TOOL: FakeTool()}):
            with self.assertLogs("mcp_audit", level="INFO") as logs:
                await asyncio.wait_for(
                    self._call_tool_over_sse(
                        {
                            "X-User-Email": "a@example.test",
                            "X-Forwarded-For": "203.0.113.1",
                        },
                        {
                            "X-User-Email": "b@example.test",
                            "X-Forwarded-For": "203.0.113.2",
                        },
                    ),
                    10,
                )

        events = _audit_events(logs)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["tool_name"], FAKE_TOOL)
        self.assertEqual(events[0]["client_ip"], "203.0.113.2")
        self.assertEqual(events[0]["user_email"], "b@example.test")

    async def test_tool_call_audit_reads_first_header_line_and_validates_ip(
        self,
    ):
        cases = [
            (
                [
                    ("X-User-Email", "b@example.test"),
                    ("X-User-Email", "c@example.test"),
                    ("X-Forwarded-For", "203.0.113.2"),
                    ("X-Forwarded-For", "198.51.100.7"),
                ],
                "203.0.113.2",
                "b@example.test",
            ),
            (
                [
                    ("X-User-Email", "b@example.test"),
                    ("X-Forwarded-For", "not-an-ip"),
                ],
                "invalid",
                "b@example.test",
            ),
        ]
        for post_headers, want_ip, want_email in cases:
            with self.subTest(post_headers=post_headers):
                with patch.dict(coordinator.tool_map, {FAKE_TOOL: FakeTool()}):
                    with self.assertLogs("mcp_audit", level="INFO") as logs:
                        await asyncio.wait_for(
                            self._call_tool_over_sse({}, post_headers), 10
                        )
                events = _audit_events(logs)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["client_ip"], want_ip)
                self.assertEqual(events[0]["user_email"], want_email)


@unittest.skipUnless(HAS_HTTP_DEPS, "HTTP MCP dependencies are not installed")
class StreamableHTTPIdentityTest(unittest.IsolatedAsyncioTestCase):
    async def test_binds_identity_from_first_header_line(self):
        seen = {}

        async def fake_handle_request(scope, receive, send):
            seen["client_ip"] = current_client_ip.get()
            seen["user_email"] = current_user_email.get()

        scope = {
            "type": "http",
            "headers": [
                (b"x-user-email", b"b@example.test"),
                (b"x-user-email", b"c@example.test"),
                (b"x-forwarded-for", b"203.0.113.2"),
                (b"x-forwarded-for", b"198.51.100.7"),
            ],
            "client": ("192.0.2.1", 1234),
        }
        with patch.object(
            server.streamable_http, "handle_request", fake_handle_request
        ):
            await server.handle_streamable_http(scope, None, None)

        self.assertEqual(
            seen,
            {"client_ip": "203.0.113.2", "user_email": "b@example.test"},
        )


class CallToolWithoutRequestTest(unittest.IsolatedAsyncioTestCase):
    async def test_audit_keeps_context_values_without_http_request(self):
        token_email = current_user_email.set("stdio@example.test")
        token_ip = current_client_ip.set("192.0.2.10")
        try:
            with patch.dict(coordinator.tool_map, {FAKE_TOOL: FakeTool()}):
                with self.assertLogs("mcp_audit", level="INFO") as logs:
                    await coordinator.call_mcp_tool(FAKE_TOOL, {})
        finally:
            current_user_email.reset(token_email)
            current_client_ip.reset(token_ip)

        events = _audit_events(logs)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["client_ip"], "192.0.2.10")
        self.assertEqual(events[0]["user_email"], "stdio@example.test")


if __name__ == "__main__":
    unittest.main()
