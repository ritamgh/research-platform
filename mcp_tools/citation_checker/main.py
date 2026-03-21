# mcp_tools/citation_checker/main.py
from dotenv import load_dotenv

load_dotenv()

from mcp_tools.citation_checker.server import mcp  # noqa: E402

if __name__ == "__main__":
    # Binds to 0.0.0.0 — deploy behind an authenticated proxy or in a network-isolated container.
    mcp.run(transport="http", host="0.0.0.0", port=9004)
