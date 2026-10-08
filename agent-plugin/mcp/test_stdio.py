"""Offline MCP wire smoke tests (2026-09-09).

Pins JSON-RPC framing and core MCP lifecycle/tool messages using authored requests
from https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle.
Run: python3 -m unittest discover -s agent-plugin/mcp -p 'test_*.py' -v
Client-specific installation is deliberately outside this protocol check.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SERVER = Path(__file__).resolve().with_name("server.py")


class StdioTests(unittest.TestCase):
    def exchange(self, messages):
        """Run the actual entry point outside the checkout, with network disabled."""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SERVER)],
                input="".join(json.dumps(message) + "\n" for message in messages),
                capture_output=True,
                text=True,
                cwd=directory,
                env={
                    **os.environ,
                    "TI_TOOLBOX_OFFLINE": "1",
                    "TI_TOOLBOX_ROOT": "",
                },
                timeout=20,
                check=True,
            )
        self.assertEqual(result.stderr, "")
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_initialize_discover_and_read_from_another_working_directory(self):
        responses = self.exchange(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "stdio-smoke", "version": "1"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "read_source_file",
                        "arguments": {"path": "tit/__init__.py"},
                    },
                },
            ]
        )
        self.assertEqual([r["id"] for r in responses], [1, 2, 3])
        self.assertTrue(all(r["jsonrpc"] == "2.0" for r in responses))
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", responses[0]["result"]["capabilities"])
        tools = responses[1]["result"]["tools"]
        self.assertIn("read_source_file", {tool["name"] for tool in tools})
        self.assertTrue(all(tool["inputSchema"]["type"] == "object" for tool in tools))
        self.assertFalse(responses[2]["result"]["isError"])
        self.assertIn("__version__", responses[2]["result"]["content"][0]["text"])

    def test_unknown_tool_returns_rpc_error_and_process_continues(self):
        responses = self.exchange(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "missing_tool"},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            ]
        )
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertEqual(responses[1], {"jsonrpc": "2.0", "id": 2, "result": {}})

    def test_tool_failure_is_content_error(self):
        responses = self.exchange(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "read_source_file",
                        "arguments": {"path": "../outside.txt"},
                    },
                },
            ]
        )
        self.assertTrue(responses[0]["result"]["isError"])
        self.assertEqual(responses[0]["result"]["content"][0]["type"], "text")


class JobsServerStdioTests(unittest.TestCase):
    def test_lists_tools_and_reports_a_missing_stack_as_a_tool_error(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("TIT_SERVER_URL", "TIT_SERVER_TOKEN")
            }
            env["PATH"] = directory  # no docker on PATH
            result = subprocess.run(
                [sys.executable, str(SERVER.with_name("jobs_server.py"))],
                input="".join(
                    json.dumps(m) + "\n"
                    for m in [
                        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {"name": "connect", "arguments": {}},
                        },
                    ]
                ),
                capture_output=True,
                text=True,
                cwd=directory,
                env=env,
                timeout=20,
                check=True,
            )
        listed, connected = [json.loads(line) for line in result.stdout.splitlines()]
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertIn("submit_job", names)
        self.assertTrue(connected["result"]["isError"])
        self.assertIn("TI-Toolbox", connected["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
