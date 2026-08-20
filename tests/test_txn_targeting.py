# SPDX-License-Identifier: MIT
"""Which transaction do the money tools actually act on?

These tools record payments and write off invoices, so the button they resolve
has to be the one the caller asked for -- not one whose accessible name merely
contains the number, and not an arbitrary member of several candidates.

The name matching here runs through Python's own ``re`` module against the
accessible names QBO renders (documented in actions.js: "View/Edit {NUM}
Receive payment More actions"), which mirrors Playwright's substring-regex
matching for ``get_by_role(name=...)``. The one thing a fake page cannot show
is Playwright's selector serializer, so that is covered by an invariant test
below and was checked separately against a live browser.
"""

import json
import re

import pytest

from test_server_helpers import load_server_module


class FakeButton:
    def __init__(self, accessible_name):
        self.name = accessible_name


class FakeLocator:
    """Locator over a fixed set of buttons, matched with the real ``re``."""

    def __init__(self, page, buttons, record=True):
        self.page = page
        self.buttons = buttons
        self.record = record

    async def count(self):
        return len(self.buttons)

    @property
    def first(self):
        return FakeLocator(self.page, self.buttons[:1], self.record)

    async def all(self):
        return [FakeLocator(self.page, [b], self.record) for b in self.buttons]

    async def click(self, **kwargs):
        if len(self.buttons) != 1:
            # Playwright's strict mode: a locator that resolves to several
            # elements refuses to click.
            raise RuntimeError(f"strict mode violation: {len(self.buttons)} elements")
        if self.record:
            self.page.clicked.append(self.buttons[0].name)


class RegexPage:
    """Page whose buttons are matched by name the way Playwright matches them."""

    def __init__(self, button_names, url="https://qbo.intuit.com/app/invoices"):
        self.url = url
        self.buttons = [FakeButton(n) for n in button_names]
        self.clicked = []

    def get_by_role(self, role, name=None):
        if role != "button":
            # Chrome for the search box and friends: present, but not a row.
            return FakeLocator(self, [FakeButton(f"<{role}>")], record=False)
        if isinstance(name, re.Pattern):
            hits = [b for b in self.buttons if name.search(b.name)]
        elif name is None:
            hits = list(self.buttons)
        else:
            hits = [b for b in self.buttons if name in b.name]
        return FakeLocator(self, hits)

    async def wait_for_selector(self, selector, timeout=None):
        # This fake page stops at the row click; no dialog is rendered.
        raise RuntimeError("no dialog in this fake page")

    async def query_selector(self, selector):
        return None

    async def goto(self, url):
        self.url = url


ROWS = [
    "View/Edit 6850 Receive payment More actions",
    "View/Edit 6851 Receive payment More actions",
    "View/Edit 685 Receive payment More actions",
]


def wire(server, monkeypatch, page):
    async def fake_get_page():
        return page

    async def fake_ensure_on_invoices(current_page):
        return None

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(server, "get_page", fake_get_page)
    monkeypatch.setattr(server, "ensure_on_invoices", fake_ensure_on_invoices)
    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)


# --- the pattern itself ----------------------------------------------------

def test_pattern_carries_no_bare_slash(monkeypatch):
    """A bare "/" makes the selector unparsable, so the query never runs.

    Playwright serializes the regex into ``button[name=/<pattern>/]`` and
    escapes only quotes and ">>", so an unescaped "/" closes the literal early
    and the whole call raises InvalidSelectorError before the page is read.
    """
    server = load_server_module(monkeypatch)
    source = server.txn_name_pattern("View/Edit", "6850").pattern
    assert "/" in source
    assert re.search(r"(?<!\\)/", source) is None


def test_pattern_matches_the_name_qbo_renders(monkeypatch):
    server = load_server_module(monkeypatch)
    pattern = server.txn_name_pattern("View/Edit", "6850")
    assert pattern.search("View/Edit 6850 Receive payment More actions")


def test_pattern_rejects_a_longer_invoice_number(monkeypatch):
    """"685" must not select the row of invoice 6850."""
    server = load_server_module(monkeypatch)
    pattern = server.txn_name_pattern("View/Edit", "685")
    assert pattern.search("View/Edit 685 Receive payment More actions")
    assert not pattern.search("View/Edit 6850 Receive payment More actions")
    assert not pattern.search("View/Edit 68512 Receive payment More actions")


def test_pattern_escapes_regex_metacharacters(monkeypatch):
    server = load_server_module(monkeypatch)
    pattern = server.txn_name_pattern("View/Edit", "68.0")
    assert pattern.search("View/Edit 68.0 Receive payment")
    assert not pattern.search("View/Edit 6810 Receive payment")


# --- resolution ------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_returns_the_single_matching_button(monkeypatch):
    server = load_server_module(monkeypatch)
    page = RegexPage(ROWS)

    locator, error = await server.resolve_txn_button(page, "View/Edit", "6850", "Invoice")

    assert error is None
    await locator.click()
    assert page.clicked == ["View/Edit 6850 Receive payment More actions"]


@pytest.mark.asyncio
async def test_resolve_refuses_an_ambiguous_match(monkeypatch):
    """Duplicate rows must stop the workflow, not pick one at random."""
    server = load_server_module(monkeypatch)
    page = RegexPage(ROWS + ["View/Edit 6850 Receive payment More actions"])

    locator, error = await server.resolve_txn_button(page, "View/Edit", "6850", "Invoice")

    assert locator is None
    assert "matches 2 rows" in error
    assert page.clicked == []


# --- through the tools -----------------------------------------------------

@pytest.mark.asyncio
async def test_receive_payment_does_not_pay_a_longer_invoice(monkeypatch):
    server = load_server_module(monkeypatch)
    page = RegexPage([n for n in ROWS if " 685 " not in n])  # 685 is not listed
    wire(server, monkeypatch, page)

    result = json.loads(await server.qb_receive_payment("685", "22500"))

    assert result["success"] is False
    assert result["error"].startswith("Invoice 685 not found in list")
    assert page.clicked == []


@pytest.mark.asyncio
async def test_receive_payment_opens_the_requested_invoice(monkeypatch):
    server = load_server_module(monkeypatch)
    page = RegexPage(ROWS)
    wire(server, monkeypatch, page)

    # The row is opened, then the fake page refuses to produce a dialog — the
    # assertion of interest is which row was clicked before that.
    json.loads(await server.qb_receive_payment("685", "22500"))

    assert page.clicked[0] == "View/Edit 685 Receive payment More actions"


@pytest.mark.asyncio
async def test_write_off_does_not_hit_a_longer_invoice(monkeypatch):
    server = load_server_module(monkeypatch)
    page = RegexPage([n for n in ROWS if " 685 " not in n])
    wire(server, monkeypatch, page)

    result = json.loads(await server.qb_write_off_invoice("685"))

    assert result["success"] is False
    assert result["error"].startswith("Invoice 685 not found in list")
    assert page.clicked == []


@pytest.mark.asyncio
async def test_batch_payments_report_the_refusal_per_invoice(monkeypatch):
    server = load_server_module(monkeypatch)
    page = RegexPage([n for n in ROWS if " 685 " not in n])
    wire(server, monkeypatch, page)

    result = json.loads(await server.qb_batch_receive_payments(
        json.dumps([{"invoiceNum": "685", "amount": "100"}])
    ))

    assert result["succeeded"] == 0
    assert result["results"][0]["error"].startswith("Invoice 685 not found in list")
    assert page.clicked == []


@pytest.mark.asyncio
async def test_delete_line_item_targets_the_named_invoice(monkeypatch):
    """The search-result button uses the "Invoice {NUM}" name, same rule."""
    server = load_server_module(monkeypatch)
    page = RegexPage(["Invoice 67530", "Invoice 6754"])
    wire(server, monkeypatch, page)

    result = json.loads(await server.qb_delete_line_item("6753", 2))

    assert result["success"] is False
    assert result["error"].startswith("Invoice 6753 not found in list")
    assert page.clicked == []
