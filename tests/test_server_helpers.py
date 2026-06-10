# SPDX-License-Identifier: MIT
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


def load_server_module(monkeypatch):
    """Import server.py with a tiny fake MCP package so tests stay local."""

    class FakeMCP:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def tool(self):
            def decorator(fn):
                return fn

            return decorator

    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = FakeMCP

    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", mcp_server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_module)

    module_path = Path(__file__).resolve().parents[1] / "server.py"
    spec = importlib.util.spec_from_file_location("qb_auto_server_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakePage:
    def __init__(self, url="https://qbo.intuit.com/app/dashboard", evaluate_result=None):
        self.url = url
        self.evaluate_result = evaluate_result or {}
        self.goto_calls = []
        self.waits = []
        self.roles = []

    async def goto(self, url):
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_selector(self, selector, timeout=None):
        self.waits.append((selector, timeout))

    async def evaluate(self, script):
        return self.evaluate_result

    def get_by_role(self, role, name=None):
        self.roles.append((role, name))
        return MissingLocator()


class MissingLocator:
    async def count(self):
        return 0


@pytest.mark.asyncio
async def test_ensure_on_invoices_navigates_when_needed(monkeypatch):
    server = load_server_module(monkeypatch)
    page = FakePage()
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)

    await server.ensure_on_invoices(page)

    assert page.goto_calls == ["https://qbo.intuit.com/app/invoices"]
    assert page.waits == [("table tbody tr", 15000)]
    assert sleep_calls == [1]


@pytest.mark.asyncio
async def test_ensure_on_invoices_skips_when_already_on_page(monkeypatch):
    server = load_server_module(monkeypatch)
    page = FakePage(url="https://qbo.intuit.com/app/invoices?filter=all")

    await server.ensure_on_invoices(page)

    assert page.goto_calls == []
    assert page.waits == []


@pytest.mark.asyncio
async def test_qb_list_invoices_filters_by_customer(monkeypatch):
    server = load_server_module(monkeypatch)
    page = FakePage(
        url="https://qbo.intuit.com/app/invoices",
        evaluate_result={
            "invoices": [
                {"num": "1001", "customer": "Acme Ltd", "amount": "$10.00"},
                {"num": "1002", "customer": "Other Co", "amount": "$20.00"},
                {"num": "1003", "customer": "ACME Services", "amount": "$30.00"},
            ],
            "count": 3,
        },
    )

    async def fake_get_page():
        return page

    async def fake_ensure_on_invoices(current_page):
        assert current_page is page

    monkeypatch.setattr(server, "get_page", fake_get_page)
    monkeypatch.setattr(server, "ensure_on_invoices", fake_ensure_on_invoices)

    result = json.loads(await server.qb_list_invoices(customer="acme"))

    assert result["count"] == 2
    assert result["filter"] == "acme"
    assert [invoice["num"] for invoice in result["invoices"]] == ["1001", "1003"]


@pytest.mark.asyncio
async def test_qb_receive_payment_returns_not_found_without_browser_actions(monkeypatch):
    server = load_server_module(monkeypatch)
    page = FakePage(url="https://qbo.intuit.com/app/invoices")

    async def fake_get_page():
        return page

    async def fake_ensure_on_invoices(current_page):
        assert current_page is page

    monkeypatch.setattr(server, "get_page", fake_get_page)
    monkeypatch.setattr(server, "ensure_on_invoices", fake_ensure_on_invoices)

    result = json.loads(await server.qb_receive_payment("9999", "100"))

    assert result == {
        "success": False,
        "error": "Invoice 9999 not found in list. May need to scroll or change filters.",
    }
    assert page.roles
