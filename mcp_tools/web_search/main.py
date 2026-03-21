import os
import sys

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("TAVILY_API_KEY"):
    print("ERROR: TAVILY_API_KEY environment variable is not set", file=sys.stderr)
    sys.exit(1)

from mcp_tools.web_search.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9001)
