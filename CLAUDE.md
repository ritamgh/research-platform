# Research Platform — Claude Code Instructions

## Subagent Review Calibration

When using `superpowers:subagent-driven-development`, calibrate review intensity by task type:

### Scaffold / config-only tasks
*(requirements.txt, pytest.ini, __init__.py, .gitignore, Dockerfiles)*
- **Skip reviews entirely.** Verify inline by reading the files yourself.

### Test-only tasks
*(adding tests to an existing file, no logic changes)*
- **One combined spec+quality pass.** Not two separate rounds.
- If 3+ tests pass without issues, approve and move on.

### Implementation tasks
*(new .py files, changes to existing logic, new endpoints)*
- **Full two-stage review** (spec compliance first, then code quality).

### Red flags that justify extra review
- Implementer reports DONE_WITH_CONCERNS
- API/library behaviour differed from the plan
- Error handling or retry logic is involved

---

## Known API Facts (web_search MCP tool)

Discovered during Task 2 — do not re-litigate these:

- FastMCP `Client.call_tool()` raises `fastmcp.exceptions.ToolError`, not `McpError`
- `Client.call_tool()` result uses `result.content[0].text`, not `result[0].text`
- `McpError` constructor: `McpError(ErrorData(code=INTERNAL_ERROR, message="..."))` using integer constants from `mcp.types`
- `asyncio.sleep` patch path: `"mcp_tools.web_search.server.asyncio.sleep"`
- Conda env name: `research-platform`
- Run tests with: `conda run -n research-platform pytest mcp_tools/web_search/tests/test_server.py -v`
