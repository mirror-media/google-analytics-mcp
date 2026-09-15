import unittest

import httpx

from analytics_mcp.server import HAS_HTTP_DEPS, starlette_app


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


if __name__ == "__main__":
    unittest.main()
