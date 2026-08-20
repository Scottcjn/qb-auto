# SPDX-License-Identifier: MIT
"""Guards the mcp>=2.0.0 import path: mcp.server.fastmcp was removed in mcp
2.0.0 and FastMCP was renamed to MCPServer in mcp.server.mcpserver. server.py
must fall back to the new location so the server keeps booting on both the
old and the new mcp package layout.
"""
import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"

EXPECTED_TOOLS = {
    "qb_page_state",
    "qb_list_invoices",
    "qb_invoice_state",
    "qb_receive_payment",
    "qb_create_invoice",
    "qb_delete_line_item",
    "qb_edit_payment_amount",
    "qb_batch_receive_payments",
    "qb_write_off_invoice",
    "qb_report",
    "qb_report_pnl",
    "qb_report_balance_sheet",
    "qb_report_ar_aging",
    "qb_report_customer_balance",
    "qb_report_open_invoices",
    "qb_report_vendor_balance",
}


class _FakeServerClass:
    """Stand-in for either FastMCP or MCPServer — same tool()/run() surface."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.tool_names = []

    def tool(self):
        def decorator(fn):
            self.tool_names.append(fn.__name__)
            return fn

        return decorator

    def run(self):
        pass


def _load_server_module(monkeypatch, hide=()):
    """Import server.py fresh, optionally hiding one of the two mcp layouts
    via a meta-path finder (sys.modules deletion alone isn't enough — Python
    would just re-import the real installed package)."""

    for name in list(sys.modules):
        if name == "server" or name.startswith("qb_auto_server_test"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = _FakeServerClass
    mcpserver_module = types.ModuleType("mcp.server.mcpserver")
    mcpserver_module.MCPServer = _FakeServerClass

    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", mcp_server_module)
    if "fastmcp" not in hide:
        monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_module)
    if "mcpserver" not in hide:
        monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", mcpserver_module)

    class _BlockHidden:
        def find_module(self, fullname, path=None):
            if fullname in ("mcp.server.fastmcp",) and "fastmcp" in hide:
                return self
            if fullname in ("mcp.server.mcpserver",) and "mcpserver" in hide:
                return self
            return None

        def load_module(self, fullname):
            raise ImportError(f"{fullname} not available (blocked for test)")

    blocker = _BlockHidden()
    sys.meta_path.insert(0, blocker)
    monkeypatch.setattr(
        sys, "meta_path", sys.meta_path, raising=False
    )  # keep reference alive for cleanup below

    try:
        spec = importlib.util.spec_from_file_location(
            "qb_auto_server_test", SERVER_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.meta_path.remove(blocker)


def test_all_tools_register(monkeypatch):
    module = _load_server_module(monkeypatch)
    assert isinstance(module.mcp, _FakeServerClass)
    assert set(module.mcp.tool_names) == EXPECTED_TOOLS


def test_survives_missing_fastmcp_module(monkeypatch):
    """mcp>=2.0.0: mcp.server.fastmcp does not exist at all."""
    module = _load_server_module(monkeypatch, hide=("fastmcp",))
    assert set(module.mcp.tool_names) == EXPECTED_TOOLS


def test_survives_missing_mcpserver_module(monkeypatch):
    """mcp<2.0.0: mcp.server.mcpserver does not exist yet, must fall back."""
    module = _load_server_module(monkeypatch, hide=("mcpserver",))
    assert set(module.mcp.tool_names) == EXPECTED_TOOLS


def test_no_unguarded_toplevel_fastmcp_import():
    """Guard against a regression back to a bare `from mcp.server.fastmcp
    import FastMCP` with no try/except fallback."""
    tree = ast.parse(SERVER_PATH.read_text())
    module_body = tree.body

    def is_bare_fastmcp_import(node):
        return (
            isinstance(node, ast.ImportFrom)
            and node.module == "mcp.server.fastmcp"
        )

    for node in module_body:
        if is_bare_fastmcp_import(node):
            pytest.fail(
                "found a top-level `from mcp.server.fastmcp import ...` "
                "outside of a try/except — this breaks on mcp>=2.0.0"
            )
        if isinstance(node, ast.Try):
            for sub in node.body:
                assert not is_bare_fastmcp_import(sub) or any(
                    isinstance(h, ast.ExceptHandler) for h in node.handlers
                )
