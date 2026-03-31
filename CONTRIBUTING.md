# Contributing to qb-auto

Thanks for helping improve `qb-auto`, the QuickBooks Online MCP server for targeted browser automation.

This repo is intentionally small. Most contributions should stay focused on one of these areas:

- `server.py` for MCP tool definitions, browser connection logic, and end-to-end QuickBooks workflows
- `extractors.js` for compact DOM extraction helpers
- `actions.js` for reusable Playwright action sequences
- `PLAYBOOK.md` for manual operator guidance and low-token usage patterns

## Before You Start

- Read [README.md](./README.md) for the current tool list and setup flow
- Read [PLAYBOOK.md](./PLAYBOOK.md) before changing extractor or action behavior
- Keep changes small and reviewable; one workflow fix or one documentation improvement per PR is ideal

## Local Setup

### Prerequisites

- Python 3.10+
- Google Chrome or Chromium
- Access to a QuickBooks Online session for real browser validation

### Install Dependencies

```bash
pip install mcp playwright
playwright install chromium
```

### Start Chrome with Remote Debugging

```bash
google-chrome --remote-debugging-port=9222
```

If you use a different port, update `QB_CDP_PORT` in your environment before launching the server.

## Running the Server

```bash
python3 server.py
```

For Claude Code / MCP registration, follow the `~/.mcp.json` example in [README.md](./README.md).

## Contribution Guidelines

### Python Changes (`server.py`)

- Keep tool behavior explicit and deterministic
- Prefer compact JSON responses over large page dumps
- Reuse existing helper patterns before adding new connection logic
- Handle failure cases clearly so operators know whether the issue is navigation, form state, or browser connectivity

### Browser Automation Changes (`actions.js`, `extractors.js`)

- Prefer ARIA selectors and stable labels over brittle CSS selectors
- Minimize token output; extract only the data needed for the workflow
- Do not add broad `browser_snapshot`-style flows when a targeted extractor or action can solve the task
- Keep QuickBooks-specific assumptions documented in comments or in `PLAYBOOK.md` when they are non-obvious

### Docs Changes

- Keep README examples aligned with the actual server behavior
- Update `PLAYBOOK.md` when you change extractor inputs, return shapes, or action signatures
- If a workflow requires a new prerequisite or env var, document it in the same PR

## Validation

Run the fastest relevant checks before opening a PR:

```bash
python3 -m py_compile server.py
```

For documentation-only changes:

```bash
git diff --check
```

For behavior changes, also do a focused real-world smoke test against an already logged-in QuickBooks browser session when possible.

Suggested manual checks:

- `qb_page_state` still returns compact page identity data
- invoice and payment flows still connect to the active browser session
- report tools still return small, structured responses instead of full-page dumps

## Pull Requests

Include these points in your PR description:

- what changed
- why the change is needed
- which file(s) were touched
- what you used to validate the change

Good PR examples for this repo:

- fix one broken workflow
- improve one extractor's returned shape
- clarify one setup or operator instruction
- add one narrowly scoped MCP tool that fits the existing architecture

## Things to Avoid

- large refactors that mix server logic, extractor changes, and docs cleanup in one PR
- adding telemetry, analytics, or network calls unrelated to QuickBooks automation
- replacing targeted extraction with expensive snapshot-based approaches
- changing tool names or argument shapes without updating docs in the same PR

## Questions

If the intended QuickBooks behavior is unclear, open an issue or describe the exact UI state in your PR so reviewers can validate the workflow quickly.
